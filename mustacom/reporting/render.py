"""Document rendering and printing.

Every printable document (devis, facture, BL, bon de route, avoir, re\u00e7u,
ticket 80 mm, relev\u00e9s, rapports...) is rendered as an HTML page into a
``QTextDocument``.  From there it can be:

* exported to PDF (``QPrinter`` in PDF mode),
* printed on any Windows printer (``QPrinter`` with a device),
* previewed in a ``QPrintPreviewDialog``.

The layout honours the company profile from Settings (logo, ICE/IF/RC, bank
coordinates, footer, legal mentions) and the current UI language - Arabic
switches the whole document to RTL.
"""

from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import (QGuiApplication, QImage, QPageLayout, QPainter,
                           QPageSize, QTextDocument)
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

from ..config import PAPER_SIZES
from ..core.money import cents_to_money, format_money
from ..i18n import I18N, tr

MM = 72.0 / 25.4    # pt per mm at 72 dpi


# ---------------------------------------------------------------------------
# paper sizes
# ---------------------------------------------------------------------------
class Paper:
    def __init__(self, code: str):
        if code not in PAPER_SIZES:
            code = "a4"
        self.code = code
        specs = {
            "a4": (210.0, 297.0, 12.0),
            "a5": (148.0, 210.0, 10.0),
            "thermal80": (80.0, 200.0, 4.0),
            "thermal58": (58.0, 200.0, 3.0),
        }
        self.width_mm, self.height_mm, self.margin_mm = specs[code]

    @property
    def is_thermal(self) -> bool:
        return self.code.startswith("thermal")

    def page_size(self) -> QSizeF:
        return QSizeF(self.width_mm, self.height_mm)


def money_symbol(services) -> str:
    return services.settings.currency_symbol()


# ---------------------------------------------------------------------------
# number in words (French) - "arr\u00eat\u00e9e \u00e0 la somme de ..."
# ---------------------------------------------------------------------------
_UNITS = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
          "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
          "dix-sept", "dix-huit", "dix-neuf"]
_TENS = ["", "dix", "vingt", "trente", "quarante", "cinquante", "soixante",
         "soixante", "quatre-vingt", "quatre-vingt"]


def _under_100(number: int) -> str:
    if number < 20:
        return _UNITS[number]
    tens, unit = number // 10, number % 10
    if tens == 7 or tens == 9:
        base = _TENS[tens]
        rest = _UNITS[10 + unit]
        joined = f"{base}-{rest}"
        return joined
    base = _TENS[tens]
    if tens in (2, 3, 4, 5, 6, 8) and unit == 1:
        return f"{base} et un"
    if tens == 8 and unit == 0:
        return "quatre-vingts"
    if unit:
        return f"{base}-{_UNITS[unit]}"
    return base


def _under_1000(number: int) -> str:
    hundreds, rest = number // 100, number % 100
    parts = []
    if hundreds:
        parts.append("cent" if hundreds == 1 else f"{_UNITS[hundreds]} cent"
                     + ("s" if hundreds > 1 and not rest else ""))
    if rest:
        parts.append(_under_100(rest))
    return " ".join(parts)


def number_to_words_fr(number: int) -> str:
    if number == 0:
        return "z\u00e9ro"
    chunks = []
    milliards, number = divmod(number, 1_000_000_000)
    millions, number = divmod(number, 1_000_000)
    milliers, number = divmod(number, 1_000)
    if milliards:
        chunks.append(f"{_under_1000(milliards)} milliard" + ("s" if milliards > 1 else ""))
    if millions:
        chunks.append(f"{_under_1000(millions)} million" + ("s" if millions > 1 else ""))
    if milliers:
        chunks.append("mille" if milliers == 1 else f"{_under_1000(milliers)} mille")
    if number:
        chunks.append(_under_1000(number))
    return " ".join(chunks)


def amount_in_words(cents: int, symbol: str = "DH") -> str:
    units, fraction = divmod(abs(cents), 100)
    text = number_to_words_fr(units)
    words = f"{text} dirham" + ("s" if units != 1 else "")
    if fraction:
        words += f" et {number_to_words_fr(fraction)} centime" + ("s" if fraction > 1 else "")
    return words


# ---------------------------------------------------------------------------
# HTML construction
# ---------------------------------------------------------------------------
def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def doc_css(paper: Paper, rtl: bool) -> str:
    direction = "rtl" if rtl else "ltr"
    base_font = 13 if paper.is_thermal else 9.5
    return f"""
    @page {{ size: {paper.width_mm}mm {paper.height_mm}mm;
             margin: {paper.margin_mm}mm; }}
    html, body {{ font-family: "Segoe UI","Noto Sans","DejaVu Sans",sans-serif;
        font-size: {base_font}pt; color: #111; direction: {direction}; }}
    table {{ border-collapse: collapse; width: 100%; }}
    .head {{ width: 100%; }}
    .company {{ font-size: {base_font + 5}pt; font-weight: 800; color: #0F766E; }}
    .sub {{ font-size: {base_font - 1}pt; color: #444; }}
    .doc-title {{ font-size: {base_font + 4}pt; font-weight: 800; text-transform: uppercase;
        border: 1.5pt solid #0F766E; color: #0F766E; padding: 4pt 10pt; display: inline-block; }}
    .box {{ border: 0.6pt solid #999; padding: 6pt; margin-top: 6pt; }}
    .lines th {{ background: #0F766E; color: #fff; padding: 4pt 5pt;
        font-size: {base_font - 1}pt; text-align: {"right" if rtl else "left"}; }}
    .lines td {{ border-bottom: 0.4pt solid #ccc; padding: 3.5pt 5pt; }}
    .num {{ text-align: {"left" if rtl else "right"}; }}
    .totals td {{ padding: 2.5pt 6pt; }}
    .total-final {{ font-weight: 800; background: #EAF6F5; }}
    .words {{ font-style: italic; font-size: {base_font - 0.5}pt; margin-top: 6pt; }}
    .sig {{ margin-top: 18pt; }}
    .sig-box {{ border: 0.6pt solid #999; height: 60pt; }}
    .footer {{ margin-top: 14pt; border-top: 0.6pt solid #999; padding-top: 5pt;
               font-size: {base_font - 2}pt; color: #555; text-align: center; }}
    .meta {{ font-size: {base_font - 1}pt; }}
    .muted {{ color: #666; }}
    .right {{ text-align: {"left" if rtl else "right"}; }}
    .center {{ text-align: center; }}
    .logo {{ max-height: 46pt; max-width: 120pt; }}
    """


def company_block(services) -> str:
    company = services.settings.company()
    logo = ""
    logo_path = company.get("company_logo_path", "")
    if logo_path and services.settings.get_bool("doc.show_logo", True) and Path(logo_path).exists():
        logo = f'<img class="logo" src="file:///{Path(logo_path).as_posix()}"/>'
    lines = [
        esc(company.get("company_name", "")),
    ]
    detail = " - ".join(part for part in [
        esc(company.get("company_activity", "")),
    ] if part)
    address = ", ".join(part for part in [
        esc(company.get("company_address", "")),
        esc(company.get("company_zip", "")),
        esc(company.get("company_city", "")),
    ] if part)
    contact = " | ".join(part for part in [
        esc(company.get("company_phone", "")),
        esc(company.get("company_email", "")),
        esc(company.get("company_website", "")),
    ] if part)
    legal = []
    if services.settings.get_bool("doc.show_ice", True):
        for key, name in (("company_ice", "ICE"), ("company_if", "IF"), ("company_rc", "RC")):
            if company.get(key):
                legal.append(f"{name}: {esc(company[key])}")
    return f"""
    <table class="head"><tr>
      <td>{logo}</td>
      <td>
        <div class="company">{lines[0]}</div>
        <div class="sub">{detail}</div>
        <div class="sub">{address}</div>
        <div class="sub">{contact}</div>
        <div class="sub muted">{' &nbsp;|&nbsp; '.join(legal)}</div>
      </td>
    </tr></table>
    """


def party_block(services, party: dict, title: str) -> str:
    if not party:
        party = {}
    rows = [f"<b>{esc(party.get('name', ''))}</b>"]
    if party.get("company") and party.get("company") != party.get("name"):
        rows.append(esc(party["company"]))
    address = ", ".join(p for p in [party.get("address", ""), party.get("zip", ""),
                                    party.get("city", "")] if p)
    if address:
        rows.append(esc(address))
    contact = " | ".join(p for p in [party.get("phone", ""), party.get("mobile", ""),
                                     party.get("email", "")] if p)
    if contact:
        rows.append(esc(contact))
    fiscal = " | ".join(f"{k}: {esc(party.get(col, ''))}" for k, col in
                        (("ICE", "ice"), ("IF", "if_number"), ("RC", "rc"))
                        if party.get(col))
    if fiscal:
        rows.append(fiscal)
    body = "<br/>".join(r for r in rows if r)
    return f'<div class="box"><div class="muted">{esc(title)}</div>{body}</div>'


def lines_table(items: list[dict], services, show_prices: bool = True,
                qty_header: str | None = None) -> str:
    symbol = money_symbol(services)
    headers = [tr("doc.designation_col"), tr("common.quantity")]
    if show_prices:
        headers += [tr("doc.pu_ht"), tr("pos.discount"), "TVA %", tr("doc.total_col")]
    html_rows = []
    for item in items:
        qty = cents_to_money_qty(item.get("quantity", item.get("qty", 0)))
        cells = [
            f"<td>{esc(item.get('label', ''))}"
            + (f"<br/><span class='muted'>{esc(item.get('code', ''))}</span>"
               if item.get("code") else "") + "</td>",
            f'<td class="num">{qty}</td>',
        ]
        if show_prices:
            unit = item.get("unit_price_cents", 0)
            line_total = item.get("line_total_cents", item.get("total_cents", 0))
            vat = Decimal(int(item.get("vat_rate_bp", 0))) / Decimal(100)
            discount = Decimal(int(item.get("discount_percent_bp", 0))) / Decimal(100)
            cells += [
                f'<td class="num">{fmt(unit, symbol)}</td>',
                f'<td class="num">{discount:g}%</td>',
                f'<td class="num">{vat:g}</td>',
                f'<td class="num">{fmt(line_total, symbol)}</td>',
            ]
        html_rows.append("<tr>" + "".join(cells) + "</tr>")
    header_html = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return f'<table class="lines"><tr>{header_html}</tr>{"".join(html_rows)}</table>'


def cents_to_money_qty(value) -> str:
    quantity = Decimal(int(value or 0)) / Decimal(1000)
    text = f"{quantity:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def fmt(cents: int, symbol: str) -> str:
    return format_money(cents_to_money(cents), symbol)


def totals_table(doc_totals: dict, services) -> str:
    symbol = money_symbol(services)
    rows = [
        (tr("common.subtotal") + " HT", doc_totals.get("subtotal_ht")),
        (tr("pos.discount"), doc_totals.get("discount")),
        (tr("pos.total_ht"), doc_totals.get("total_ht")),
    ]
    breakdown = doc_totals.get("vat_breakdown", {})
    if breakdown:
        for rate, amount in breakdown.items():
            rows.append((f"TVA {rate} %", amount))
    else:
        rows.append((tr("pos.total_vat"), doc_totals.get("total_vat")))
    html_rows = "".join(
        f'<tr><td class="right muted">{esc(name)}</td>'
        f'<td class="num">{esc(amount) if isinstance(amount, str) else fmt(_to_cents(amount), symbol)}</td></tr>'
        for name, amount in rows if amount)
    total_row = (
        f'<tr class="total-final"><td class="right">{esc(tr("pos.total_ttc"))}</td>'
        f'<td class="num">{fmt(_to_cents(doc_totals.get("total_ttc")), symbol)}</td></tr>')
    return f'<table class="totals" align="{"left" if I18N.is_rtl else "right"}" ' \
           f'style="width:60%">{html_rows}{total_row}</table>'


def _to_cents(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value * 100)
    text = (str(value).strip().replace("\u00a0", " ").replace(" ", "")
            .replace(",", "."))
    if not text:
        return 0
    return int(Decimal(text) * 100)


def signature_block(services, two: bool = True) -> str:
    company = services.settings.company()
    stamp = company.get("company_stamp_path", "")
    signature = company.get("company_signature_path", "")
    images = ""
    for path in (stamp, signature):
        if path and Path(path).exists():
            images += f'<img style="max-height:40pt" src="file:///{Path(path).as_posix()}"/>'
    left = f"""<td style="width:50%"><b>{esc(company.get("company_name", ''))}</b><br/>
               {images}<div class="sig-box"></div></td>"""
    right = f"""<td style="width:50%">{esc(tr('common.signature_area'))}
                <div class="sig-box"></div></td>"""
    if not two:
        return f'<table class="sig"><tr>{right}</tr></table>'
    return f'<table class="sig"><tr>{left}{right}</tr></table>'


def footer_block(services) -> str:
    company = services.settings.company()
    parts = [p for p in [company.get("document_footer", ""),
                         company.get("document_legal", "")] if p]
    bank = " - ".join(p for p in [company.get("company_bank_name", ""),
                                  company.get("company_bank_rib", "")] if p)
    if bank:
        parts.append(f"{tr('settings.bank')} : {esc(bank)}")
    printed = datetime.now().strftime("%d/%m/%Y %H:%M")
    parts.append(tr("doc.printed_on", date=printed))
    return f'<div class="footer">{"<br/>".join(esc(p) for p in parts)}</div>'


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------
def totals_from_doc(doc: dict) -> dict:
    """Copy of ``doc["totals"]`` normalised for display.

    Values stay numeric (int cents / Decimal money) so that ``_to_cents`` can
    convert them; pre-formatted strings are passed through untouched.
    """
    return dict(doc.get("totals", {}))


def render_document(services, kind: str, doc: dict, paper: str = "a4") -> QTextDocument:
    """Build the QTextDocument for a stored business document."""
    paper_obj = Paper(paper)
    rtl = I18N.is_rtl
    symbol = money_symbol(services)
    titles = {
        "quote": tr("doc.devis"), "order_client": tr("doc.bc_client"),
        "order_supplier": tr("doc.bc_supplier"), "delivery": tr("doc.bl"),
        "route": tr("doc.br"), "invoice": tr("doc.invoice"),
        "proforma": tr("doc.proforma"), "credit_note": tr("doc.credit_note"),
        "return_client": "Bon de retour client",
        "return_supplier": "Bon de retour fournisseur",
        "purchase": tr("doc.purchase_order"),
        "purchase_invoice": tr("doc.purchase_invoice"),
        "receipt": tr("doc.receipt"), "repair": tr("doc.repair_receipt"),
        "statement_customer": tr("doc.customer_statement"),
        "statement_supplier": tr("doc.supplier_statement"),
        "receipt_note": tr("doc.receipt_note"),
    }
    title = titles.get(kind, kind)

    meta_rows = [(tr("doc.number"), doc.get("number", "")),
                 (tr("common.date"), str(doc.get("date", ""))[:10])]
    for key, label_key in (("valid_until", "doc.valid_until"), ("due_date", "doc.due_date"),
                           ("expected_date", "common.to")):
        if doc.get(key):
            meta_rows.append((tr(label_key), str(doc[key])[:10]))

    body = [company_block(services)]
    body.append(f'<table style="width:100%;margin-top:8pt"><tr>'
                f'<td><span class="doc-title">{esc(title)}</span>'
                f'<div class="meta" style="margin-top:4pt">'
                + "".join(f"<div>{esc(k)} : <b>{esc(v)}</b></div>" for k, v in meta_rows)
                + "</div></td>"
                f'<td style="width:45%">{party_block(services, doc.get("party", {}), tr("customers.title"))}</td>'
                f'</tr></table>')

    items = doc.get("items", [])
    if kind == "route":
        extra = doc.get("extra", {})
        body.append('<table class="lines" style="margin-top:8pt"><tr>'
                    + "".join(f"<th>{esc(h)}</th>" for h in
                              [tr("doc.driver"), tr("doc.vehicle"), tr("doc.registration"),
                               tr("doc.departure"), tr("doc.destination"), tr("doc.km")])
                    + "</tr><tr>"
                    + "".join(f"<td>{esc(extra.get(k, ''))}</td>"
                              for k in ("driver", "vehicle", "registration",
                                        "departure", "destination", "km"))
                    + "</tr></table>")
        body.append(lines_table(items, services, show_prices=False))
    elif kind in ("statement_customer", "statement_supplier"):
        body.append(statement_table(doc.get("entries", []), services, kind))
    elif kind == "delivery":
        body.append(lines_table(items, services, show_prices=False))
    else:
        body.append('<div style="margin-top:8pt">' + lines_table(items, services) + "</div>")

    totals = totals_from_doc(doc)
    if kind not in ("route", "delivery", "statement_customer", "statement_supplier"):
        body.append('<div style="margin-top:6pt">' + totals_table(totals, services) + "</div>")
        if not paper_obj.is_thermal and totals.get("total_ttc"):
            words = amount_in_words(_to_cents(doc.get("total_cents",
                                                      totals.get("total_ttc", 0))), symbol)
            body.append(f'<div class="words">{esc(tr("doc.stopped_words"))} : '
                        f'<b>{esc(words)}</b></div>')

    if kind in ("invoice", "proforma", "credit_note") and not paper_obj.is_thermal:
        paid = _to_cents(doc.get("paid_cents", 0))
        if paid:
            body.append(f'<div class="meta">{esc(tr("doc.amount_paid"))} : '
                        f'{fmt(paid, symbol)} &nbsp;&nbsp; {esc(tr("doc.remaining_amount"))} : '
                        f'{fmt(_to_cents(doc.get("total_cents", 0)) - paid, symbol)}</div>')
        terms = doc.get("terms") or services.settings.get("payment_conditions", "")
        if terms:
            body.append(f'<div class="meta muted">{esc(tr("settings.payment_conditions"))} : '
                        f'{esc(terms)}</div>')

    if doc.get("notes"):
        body.append(f'<div class="meta" style="margin-top:6pt"><b>{esc(tr("common.notes"))} :'
                    f'</b> {esc(doc["notes"])}</div>')

    if not paper_obj.is_thermal:
        body.append(signature_block(services, two=kind in ("invoice", "delivery", "route",
                                                           "quote", "order_client")))
    body.append(footer_block(services))

    document = QTextDocument()
    document.setDocumentMargin(0)
    document.setDefaultStyleSheet(doc_css(paper_obj, rtl))
    document.setHtml("".join(body))
    page = QPageSize(paper_obj.page_size(), QPageSize.Unit.Millimeter)
    document.setPageSize(page.size(QPageSize.Unit.Point))
    return document


def statement_table(entries: list[dict], services, kind: str) -> str:
    symbol = money_symbol(services)
    headers = [tr("common.date"), tr("common.label"), tr("common.reference"),
               "D\u00e9bit", "Cr\u00e9dit", "Solde"]
    rows = []
    running = 0
    for entry in entries:
        debit = entry.get("debit_cents", 0)
        credit = entry.get("credit_cents", 0)
        running += entry.get("balance_cents", 0)
        rows.append("<tr>"
                    + f'<td>{esc(str(entry.get("date", ""))[:10])}</td>'
                    + f'<td>{esc(entry.get("label", ""))}</td>'
                    + f'<td>{esc(entry.get("number", ""))}</td>'
                    + f'<td class="num">{fmt(debit, symbol) if debit else ""}</td>'
                    + f'<td class="num">{fmt(credit, symbol) if credit else ""}</td>'
                    + f'<td class="num">{fmt(running, symbol)}</td>'
                    + "</tr>")
    header = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return f'<table class="lines" style="margin-top:8pt"><tr>{header}</tr>{"".join(rows)}</table>'


# ---------------------------------------------------------------------------
# thermal receipt
# ---------------------------------------------------------------------------
def render_receipt(services, sale: dict, paper: str = "thermal80") -> QTextDocument:
    return render_document(services, "receipt", sale, paper)


# ---------------------------------------------------------------------------
# export / print helpers
# ---------------------------------------------------------------------------
def document_to_pdf(services, document: QTextDocument, destination: Path | str,
                    paper: str = "a4") -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(destination))
    paper_obj = Paper(paper)
    printer.setPageSize(QPageSize(paper_obj.page_size(), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(paper_obj.margin_mm, paper_obj.margin_mm,
                                     paper_obj.margin_mm, paper_obj.margin_mm),
                           QPageLayout.Unit.Millimeter)
    document.print_(printer)
    return destination


def available_printers() -> list[str]:
    return [p.printerName() for p in QPrinterInfo.availablePrinters()]


def print_document(document: QTextDocument, printer_name: str = "",
                   copies: int = 1, paper: str = "a4") -> bool:
    printer = QPrinter(QPrinter.HighResolution)
    if printer_name:
        info = QPrinterInfo.printerInfo(printer_name)
        if not info.isNull():
            printer.setPrinterName(printer_name)
    printer.setPrintRange(QPrinter.PrintRange.AllPages)
    printer.setCopyCount(max(1, int(copies)))
    paper_obj = Paper(paper)
    printer.setPageSize(QPageSize(paper_obj.page_size(), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(paper_obj.margin_mm, paper_obj.margin_mm,
                                     paper_obj.margin_mm, paper_obj.margin_mm),
                           QPageLayout.Unit.Millimeter)
    document.print_(printer)
    return printer.printerState() != QPrinter.PrinterState.ErrorState


def document_to_image(document: QTextDocument, page: int = 0, dpi: int = 100) -> QImage:
    size = document.pageSize()
    scale = dpi / 72.0
    image = QImage(int(size.width() * scale), int(size.height() * scale),
                   QImage.Format.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.scale(scale, scale)
    document.drawContents(painter)
    painter.end()
    return image


def register_document(services, doc_type: str, doc_id: int, pdf_path: Path) -> None:
    services.db.insert("documents", doc_type=doc_type, doc_id=doc_id, kind="pdf",
                       file_path=str(pdf_path), created_by=services.user_id)
