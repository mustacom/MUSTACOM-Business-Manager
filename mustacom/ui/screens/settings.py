"""Paramètres: entreprise, taxes, numérotation, devise/langue, impression,
POS, apparence, base de données."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ...config import DOCUMENT_PREFIXES
from ...i18n import I18N, tr
from ..widgets.common import button, card, error, info, label, scroll
from .base import BaseScreen


class SettingsScreen(BaseScreen):
    module = "settings"
    subtitle = tr("settings.title")

    def build(self) -> None:
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self._build_company()
        self._build_tax()
        self._build_locale()
        self._build_print()
        self._build_pos()
        self._build_appearance()
        self._build_database()
        super().build()

    # ------------------------------------------------------------------
    def _add_tab(self, widget: QWidget, name: str) -> None:
        self.tabs.addTab(scroll(widget), name)

    def _build_company(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        company = self.services.settings.company()
        self.company_fields: dict[str, QLineEdit] = {}
        captions = [
            ("company_name", tr("settings.company_name")),
            ("company_legal_form", tr("settings.legal_form")),
            ("company_activity", tr("settings.activity")),
            ("company_address", tr("customers.address")),
            ("company_zip", tr("customers.zip")),
            ("company_city", tr("customers.city")),
            ("company_country", tr("customers.country")),
            ("company_phone", tr("customers.phone")),
            ("company_email", tr("customers.email")),
            ("company_website", "Web"),
            ("company_ice", "ICE"), ("company_if", "IF"), ("company_rc", "RC"),
            ("company_cnss", "CNSS"), ("company_patente", tr("settings.patente")),
            ("company_capital", tr("settings.capital")),
            ("company_bank_name", tr("settings.bank")),
            ("company_bank_rib", tr("settings.rib")),
            ("company_bank_swift", "SWIFT"),
        ]
        for key, caption in captions:
            field = QLineEdit(str(company.get(key, "")))
            self.company_fields[key] = field
            form.addRow(caption, field)
        for key, caption in (("company_logo_path", tr("settings.logo")),
                             ("company_stamp_path", tr("settings.stamp")),
                             ("company_signature_path", tr("settings.signature"))):
            field = QLineEdit(str(company.get(key, "")))
            self.company_fields[key] = field
            row = QHBoxLayout()
            row.addWidget(field, 1)
            browse = QPushButton("\U0001F4C1")
            browse.setFixedWidth(36)
            browse.clicked.connect(lambda _c, k=key: self._pick_image(k))
            row.addWidget(browse)
            wrap = QWidget()
            wrap.setLayout(row)
            form.addRow(caption, wrap)
        self.footer = QLineEdit(self.services.settings.get("pos.receipt_footer", ""))
        form.addRow(tr("settings.receipt_footer"), self.footer)
        save = button(tr("common.save"), self._save_company, kind="primary")
        form.addRow(save)
        self._add_tab(page, tr("settings.company"))

    def _pick_image(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("settings.logo"), str(self.services.paths.data),
            "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.company_fields[key].setText(path)

    def _save_company(self) -> None:
        if not self.require("edit"):
            return
        values = {f"company.{key}": field.text().strip()
                  for key, field in self.company_fields.items()}
        values["pos.receipt_footer"] = self.footer.text()
        self.services.settings.set_many(values, user_id=self.services.user_id)
        self.services.log("settings.company", details="profil entreprise")
        info(self, tr("common.saved_ok"), tr("common.success"))

    # ------------------------------------------------------------------
    def _build_tax(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.vat_default = self._spin(self.services.settings.get_float(
            "tax.default_vat_rate", 20.0))
        form.addRow(tr("settings.vat_default"), self.vat_default)
        self.vat_standard = self._spin(self.services.settings.get_float(
            "tax.vat_standard", 20.0))
        self.vat_reduced = self._spin(self.services.settings.get_float(
            "tax.vat_reduced", 10.0))
        self.vat_zero = self._spin(self.services.settings.get_float("tax.vat_zero", 0.0))
        form.addRow(tr("settings.vat_standard"), self.vat_standard)
        form.addRow(tr("settings.vat_reduced"), self.vat_reduced)
        form.addRow(tr("settings.vat_zero"), self.vat_zero)

        form.addRow(label(tr("settings.numbering_prefixes"), "CardTitle"))
        self.prefix_fields: dict[str, QLineEdit] = {}
        from datetime import date

        year = date.today().year
        for doc_type, default in DOCUMENT_PREFIXES.items():
            stored = self.services.db.scalar(
                "SELECT prefix FROM document_sequences WHERE doc_type=? AND year=?",
                (doc_type, year)) or default
            field = QLineEdit(stored)
            self.prefix_fields[doc_type] = field
            caption = tr(f"doctype.{doc_type}")
            form.addRow(caption if caption != f"doctype.{doc_type}" else doc_type, field)
        save = button(tr("common.save"), self._save_tax, kind="primary")
        form.addRow(save)
        self._add_tab(page, tr("settings.tax_numbering"))

    def _spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSuffix(" %")
        spin.setValue(float(value))
        return spin

    def _save_tax(self) -> None:
        if not self.require("edit"):
            return
        self.services.settings.set_many({
            "tax.default_vat_rate": self.vat_default.value(),
            "tax.vat_standard": self.vat_standard.value(),
            "tax.vat_reduced": self.vat_reduced.value(),
            "tax.vat_zero": self.vat_zero.value(),
        }, user_id=self.services.user_id)
        from datetime import date

        year = date.today().year
        for doc_type, field in self.prefix_fields.items():
            prefix = field.text().strip().upper()
            if not prefix:
                continue
            row_id = self.services.db.scalar(
                "SELECT id FROM document_sequences WHERE doc_type=? AND year=?",
                (doc_type, year))
            if row_id:
                self.services.db.update("document_sequences", row_id, prefix=prefix)
            else:
                self.services.db.insert("document_sequences", doc_type=doc_type,
                                        year=year, counter=0, prefix=prefix)
        self.services.log("settings.tax", details="taux + numérotation")
        info(self, tr("common.saved_ok"), tr("common.success"))

    # ------------------------------------------------------------------
    def _build_locale(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.language = QComboBox()
        for code, name in (("fr", "Fran\u00e7ais"), ("ar", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629"),
                           ("en", "English")):
            self.language.addItem(name, code)
        index = self.language.findData(self.services.settings.get("locale.language", "fr"))
        self.language.setCurrentIndex(max(0, index))
        form.addRow(tr("settings.language"), self.language)
        self.currency_code = QLineEdit(self.services.settings.get("locale.currency_code",
                                                                  "MAD"))
        form.addRow(tr("settings.currency_code"), self.currency_code)
        self.currency_symbol = QLineEdit(self.services.settings.get(
            "locale.currency_symbol", "DH"))
        form.addRow(tr("settings.currency_symbol"), self.currency_symbol)
        self.timezone = QLineEdit(self.services.settings.get("locale.timezone",
                                                             "Africa/Casablanca"))
        form.addRow(tr("settings.timezone"), self.timezone)
        self.date_format = QLineEdit(self.services.settings.get("locale.date_format",
                                                                "dd/MM/yyyy"))
        form.addRow(tr("settings.date_format"), self.date_format)
        save = button(tr("common.save"), self._save_locale, kind="primary")
        form.addRow(save)
        self._add_tab(page, tr("settings.locale"))

    def _save_locale(self) -> None:
        if not self.require("edit"):
            return
        self.services.settings.set_many({
            "locale.language": self.language.currentData(),
            "locale.currency_code": self.currency_code.text().strip(),
            "locale.currency_symbol": self.currency_symbol.text().strip(),
            "locale.timezone": self.timezone.text().strip(),
            "locale.date_format": self.date_format.text().strip(),
        }, user_id=self.services.user_id)
        self.services.log("settings.locale", details=self.language.currentData())
        info(self, tr("settings.language_restart"), tr("common.success"))
        I18N.set_language(self.language.currentData())

    # ------------------------------------------------------------------
    def _build_print(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        from ...reporting.render import available_printers

        printers = [""] + available_printers()
        self.default_printer = QComboBox()
        self.default_printer.addItems(printers)
        current = self.services.settings.get("print.default_printer", "")
        index = self.default_printer.findText(current)
        if index >= 0:
            self.default_printer.setCurrentIndex(index)
        form.addRow(tr("settings.default_printer"), self.default_printer)
        self.receipt_printer = QComboBox()
        self.receipt_printer.addItems(printers)
        current = self.services.settings.get("print.receipt_printer", "")
        index = self.receipt_printer.findText(current)
        if index >= 0:
            self.receipt_printer.setCurrentIndex(index)
        form.addRow(tr("settings.receipt_printer"), self.receipt_printer)
        self.invoice_paper = QComboBox()
        self.receipt_paper = QComboBox()
        for combo, key in ((self.invoice_paper, "print.invoice_paper"),
                           (self.receipt_paper, "print.receipt_paper")):
            for code, name in (("a4", "A4"), ("a5", "A5"),
                               ("thermal80", "80 mm"), ("thermal58", "58 mm")):
                combo.addItem(name, code)
            index = combo.findData(self.services.settings.get(key, "a4"))
            if index >= 0:
                combo.setCurrentIndex(index)
        form.addRow(tr("settings.invoice_paper"), self.invoice_paper)
        form.addRow(tr("settings.receipt_paper"), self.receipt_paper)
        self.copies_invoice = QSpinBox()
        self.copies_invoice.setRange(1, 10)
        self.copies_invoice.setValue(self.services.settings.get_int(
            "print.copies_invoice", 1))
        form.addRow(tr("settings.copies_invoice"), self.copies_invoice)
        self.copies_receipt = QSpinBox()
        self.copies_receipt.setRange(1, 10)
        self.copies_receipt.setValue(self.services.settings.get_int(
            "print.copies_receipt", 1))
        form.addRow(tr("settings.copies_receipt"), self.copies_receipt)
        self.show_logo = QCheckBox(tr("settings.show_logo"))
        self.show_logo.setChecked(self.services.settings.get_bool("doc.show_logo", True))
        form.addRow("", self.show_logo)
        save = button(tr("common.save"), self._save_print, kind="primary")
        form.addRow(save)
        self._add_tab(page, tr("settings.printing"))

    def _save_print(self) -> None:
        if not self.require("edit"):
            return
        self.services.settings.set_many({
            "print.default_printer": self.default_printer.currentText(),
            "print.receipt_printer": self.receipt_printer.currentText(),
            "print.invoice_paper": self.invoice_paper.currentData(),
            "print.receipt_paper": self.receipt_paper.currentData(),
            "print.copies_invoice": self.copies_invoice.value(),
            "print.copies_receipt": self.copies_receipt.value(),
            "doc.show_logo": self.show_logo.isChecked(),
        }, user_id=self.services.user_id)
        self.services.log("settings.print", details="imprimantes")
        info(self, tr("common.saved_ok"), tr("common.success"))

    # ------------------------------------------------------------------
    def _build_pos(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.allow_negative = QCheckBox(tr("settings.allow_negative_stock"))
        self.allow_negative.setChecked(self.services.settings.get_bool(
            "pos.allow_negative_stock", False))
        form.addRow("", self.allow_negative)
        self.require_session = QCheckBox(tr("settings.require_cash_session"))
        self.require_session.setChecked(self.services.settings.get_bool(
            "pos.require_cash_session", True))
        form.addRow("", self.require_session)
        self.auto_drawer = QCheckBox(tr("settings.auto_open_drawer"))
        self.auto_drawer.setChecked(self.services.settings.get_bool(
            "pos.auto_open_drawer", False))
        form.addRow("", self.auto_drawer)
        self.session_timeout = QSpinBox()
        self.session_timeout.setRange(0, 480)
        self.session_timeout.setSuffix(" min")
        self.session_timeout.setValue(self.services.settings.get_int(
            "security.session_timeout_minutes", 0))
        form.addRow(tr("settings.session_timeout"), self.session_timeout)
        save = button(tr("common.save"), self._save_pos, kind="primary")
        form.addRow(save)
        self._add_tab(page, tr("settings.pos_security"))

    def _save_pos(self) -> None:
        if not self.require("edit"):
            return
        self.services.settings.set_many({
            "pos.allow_negative_stock": self.allow_negative.isChecked(),
            "pos.require_cash_session": self.require_session.isChecked(),
            "pos.auto_open_drawer": self.auto_drawer.isChecked(),
            "security.session_timeout_minutes": self.session_timeout.value(),
        }, user_id=self.services.user_id)
        self.services.log("settings.pos", details="options POS")
        info(self, tr("common.saved_ok"), tr("common.success"))

    # ------------------------------------------------------------------
    def _build_appearance(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.theme = QComboBox()
        self.theme.addItem(tr("settings.theme_light"), "light")
        self.theme.addItem(tr("settings.theme_dark"), "dark")
        index = self.theme.findData(self.services.settings.get("appearance.theme",
                                                               "light"))
        self.theme.setCurrentIndex(max(0, index))
        form.addRow(tr("settings.theme"), self.theme)
        apply_now = button(tr("settings.apply_theme"), self._apply_theme, kind="primary")
        form.addRow(apply_now)
        self._add_tab(page, tr("settings.appearance"))

    def _apply_theme(self) -> None:
        if not self.require("edit"):
            return
        theme = self.theme.currentData()
        self.services.settings.set("appearance.theme", theme, self.services.user_id)
        from .. import theme as theme_module

        from PySide6.QtWidgets import QApplication

        theme_module.install(QApplication.instance(), theme == "dark")
        info(self, tr("common.saved_ok"), tr("common.success"))

    # ------------------------------------------------------------------
    def _build_database(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        db_path = self.services.db.path
        form.addRow(tr("settings.db_path"), label(str(db_path)))
        size = db_path.stat().st_size if db_path.exists() else 0
        self.db_size_label = label(f"{size / 1024:.1f} Ko")
        form.addRow(tr("settings.db_size"), self.db_size_label)
        actions = QHBoxLayout()
        actions.addWidget(button(tr("settings.integrity_check"), self._integrity))
        actions.addWidget(button(tr("backup.vacuum"), self._vacuum))
        actions.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(actions)
        form.addRow(wrap)
        self.integrity_label = label("")
        form.addRow(self.integrity_label)
        self._add_tab(page, tr("settings.database"))

    def _integrity(self) -> None:
        result = self.services.db.scalar("PRAGMA integrity_check")
        ok = result == "ok"
        self.integrity_label.setText(
            f"<b style='color:{'#15803D' if ok else '#C0392B'}'>{result}</b>")
        self.services.log("db.integrity", details=str(result))

    def _vacuum(self) -> None:
        if not self.require("edit"):
            return
        self.services.db.execute("VACUUM")
        size = self.services.db.path.stat().st_size
        self.db_size_label.setText(f"{size / 1024:.1f} Ko")
        info(self, tr("common.saved_ok"), tr("common.success"))
