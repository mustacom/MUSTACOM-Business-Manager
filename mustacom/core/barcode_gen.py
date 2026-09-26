"""Barcode / QR generation and label sheet rendering.

EAN-13 and EAN-8 checksums are computed here; the actual drawing is done by
``python-barcode`` (vector writers) and ``qrcode``.  Label sheets are laid out
on a QTextDocument so they print on any A4 printer with N labels per page.
"""

from __future__ import annotations

import io
from decimal import Decimal

from PySide6.QtGui import QImage, QTextDocument

from ..core.money import cents_to_money, format_money


# ---------------------------------------------------------------------------
# checksums
# ---------------------------------------------------------------------------
def _ean_check_digit(digits: str) -> int:
    total = 0
    for index, character in enumerate(reversed(digits)):
        weight = 3 if index % 2 == 0 else 1
        total += int(character) * weight
    return (10 - total % 10) % 10


def ean13_check_digit(payload12: str) -> int:
    if len(payload12) != 12 or not payload12.isdigit():
        raise ValueError("EAN-13 payload must be 12 digits")
    return _ean_check_digit(payload12)


def ean8_check_digit(payload7: str) -> int:
    if len(payload7) != 7 or not payload7.isdigit():
        raise ValueError("EAN-8 payload must be 7 digits")
    return _ean_check_digit(payload7)


def generate_ean13(seed: str, country: str = "611") -> str:
    """Deterministic EAN-13 (Morocco prefix 611) derived from any seed."""
    digits = "".join(ch if ch.isdigit() else str(ord(ch) % 10) for ch in seed)
    payload = (country + digits)[:12].ljust(12, "0")
    return payload + str(ean13_check_digit(payload))


def validate_ean13(code: str) -> bool:
    code = code.strip()
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == int(code[12])


def validate_ean8(code: str) -> bool:
    code = code.strip()
    return len(code) == 8 and code.isdigit() and ean8_check_digit(code[:7]) == int(code[7])


# ---------------------------------------------------------------------------
# image writers
# ---------------------------------------------------------------------------
def barcode_image(value: str, fmt: str = "code128", height_mm: float = 14) -> QImage:
    """Render a barcode to a QImage (transparent background)."""
    import barcode as pybarcode
    from barcode.writer import ImageWriter

    if fmt == "ean13":
        if not value.isdigit():
            value = generate_ean13(value)
        value = value[:12] + str(ean13_check_digit(value[:12]))
        writer = pybarcode.get("ean13", value, writer=ImageWriter())
    elif fmt == "ean8":
        value = value[:7] + str(ean8_check_digit(value[:7]))
        writer = pybarcode.get("ean8", value, writer=ImageWriter())
    else:
        writer = pybarcode.get("code128", value, writer=ImageWriter())
    buffer = io.BytesIO()
    writer.write(buffer, options={"write_text": True, "module_height": height_mm / 25.4 * 72 / 10,
                                  "font_size": 9, "quiet_zone": 2})
    buffer.seek(0)
    image = QImage()
    image.loadFromData(buffer.read())
    return image


def qr_image(value: str, size: int = 220) -> QImage:
    import qrcode

    factory = qrcode.image.pil.PilImage if hasattr(qrcode.image, "pil") else None
    img = qrcode.make(value)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    image = QImage()
    image.loadFromData(buffer.read())
    return image.scaled(size, size)


# ---------------------------------------------------------------------------
# label sheet
# ---------------------------------------------------------------------------
LABEL_SIZES = {
    "small": (38, 25),
    "medium": (50, 30),
    "large": (70, 40),
}


def label_sheet(services, entries: list[dict], label_size: str = "medium",
                fmt: str = "ean13", show_price: bool = True,
                show_name: bool = True) -> QTextDocument:
    """``entries``: list of {"value", "name", "price_cents", "copies"}."""
    width_mm, height_mm = LABEL_SIZES.get(label_size, LABEL_SIZES["medium"])
    columns = int(190 // width_mm)
    rows = int(277 // height_mm)
    symbol = services.settings.currency_symbol()

    html_labels = []
    for entry in entries:
        for _ in range(int(entry.get("copies", 1))):
            image = barcode_image(entry["value"], fmt)
            parts = []
            if show_name:
                parts.append(f"<div style='font-size:6.5pt;white-space:nowrap;overflow:hidden'>"
                             f"{_esc(entry.get('name', ''))}</div>")
            parts.append(f"<img src='data:image/png;base64,{_b64(image)}' "
                         f"style='max-width:{width_mm - 4}mm;max-height:{height_mm * 0.55}mm'/>")
            if show_price and entry.get("price_cents"):
                parts.append(f"<div style='font-size:7.5pt;font-weight:800'>"
                             f"{format_money(cents_to_money(entry['price_cents']), symbol)}</div>")
            html_labels.append(
                f"<td style='width:{width_mm}mm;height:{height_mm}mm;border:0.4pt solid #ccc;"
                f"padding:1mm;text-align:center;vertical-align:middle'>" + "".join(parts) + "</td>")

    pages = []
    per_page = columns * rows
    for start in range(0, len(html_labels), per_page):
        chunk = html_labels[start:start + per_page]
        table_rows = []
        for index in range(0, len(chunk), columns):
            cells = chunk[index:index + columns]
            while len(cells) < columns:
                cells.append(f"<td style='width:{width_mm}mm;height:{height_mm}mm'></td>")
            table_rows.append("<tr>" + "".join(cells) + "</tr>")
        pages.append(f"<table style='border-collapse:collapse;page-break-after:always'>"
                     + "".join(table_rows) + "</table>")

    document = QTextDocument()
    document.setHtml("".join(pages))
    from PySide6.QtGui import QPageSize
    from PySide6.QtCore import QSizeF

    document.setPageSize(QPageSize(QSizeF(210, 297), QPageSize.Unit.Millimeter)
                         .size(QPageSize.Unit.Point))
    return document


def _esc(value: str) -> str:
    import html as _html

    return _html.escape(str(value))


def _b64(image: QImage) -> str:
    from PySide6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data().toBase64()).decode("ascii")
