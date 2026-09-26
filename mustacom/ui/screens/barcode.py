"""Barcode module: generate EAN-13/EAN-8/Code128/QR and print label sheets."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QTextEdit, QVBoxLayout,
                               QWidget)

from ...core import barcode_gen
from ...i18n import tr
from ..dialogs.print_dialog import PrintDialog
from ..widgets.common import button, card, info, label, scroll
from .base import BaseScreen


class BarcodeScreen(BaseScreen):
    module = "barcode"
    subtitle = tr("barcode.title")

    def build(self) -> None:
        self.pending: list[dict] = []

        left = card(tr("barcode.value"))
        form = QFormLayout()
        outer = left.layout()
        outer.addLayout(form)
        self.format = QComboBox()
        for code, name in (("ean13", "EAN-13"), ("ean8", "EAN-8"),
                           ("code128", "Code 128"), ("qr", "QR Code")):
            self.format.addItem(name, code)
        form.addRow(tr("barcode.format"), self.format)
        self.value = QLineEdit()
        self.value.setPlaceholderText("6111234500017")
        form.addRow(tr("barcode.value"), self.value)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText(tr("pos.search_product"))
        self.product_search.returnPressed.connect(self._search_product)
        form.addRow(tr("products.title"), self.product_search)
        self.found = QLabel("")
        self.found.setWordWrap(True)
        form.addRow("", self.found)
        self.copies = QSpinBox()
        self.copies.setRange(1, 500)
        self.copies.setValue(10)
        form.addRow(tr("barcode.copies"), self.copies)
        self.label_size = QComboBox()
        for code, name in (("small", "38 \u00d7 25 mm"), ("medium", "50 \u00d7 30 mm"),
                           ("large", "70 \u00d7 40 mm")):
            self.label_size.addItem(name, code)
        form.addRow(tr("barcode.label_size"), self.label_size)
        self.show_price = QCheckBox(tr("barcode.show_price"))
        self.show_price.setChecked(True)
        form.addRow("", self.show_price)
        self.show_name = QCheckBox(tr("barcode.show_name"))
        self.show_name.setChecked(True)
        form.addRow("", self.show_name)
        add = button(tr("common.add"), self._add_entry, kind="primary")
        form.addRow("", add)

        right = card(tr("barcode.preview"))
        right_layout = right.layout()
        self.list = QTextEdit()
        self.list.setReadOnly(True)
        right_layout.addWidget(self.list)
        actions = QHBoxLayout()
        actions.addWidget(button(tr("barcode.print_labels"), self._print, kind="primary",
                                 icon="\U0001F5A8"))
        actions.addWidget(button(tr("common.delete"), self._clear, kind="danger"))
        right_layout.addLayout(actions)

        body = QHBoxLayout()
        body.addWidget(left, 2)
        body.addWidget(right, 3)
        self.root.addLayout(body, 1)
        super().build()

    # ------------------------------------------------------------------
    def add_product(self, product: dict) -> None:
        value = product.get("barcode") or product.get("sku")
        if product.get("barcode"):
            self.format.setCurrentIndex(self.format.findData("ean13"))
        else:
            self.format.setCurrentIndex(self.format.findData("code128"))
        self.value.setText(value)
        self._add_entry(name=product.get("name"), price=product.get("sale_price_cents"))

    def _search_product(self) -> None:
        term = self.product_search.text().strip()
        results = self.services.sales.search(term, limit=5)
        if not results:
            self.found.setText(tr("common.no_data"))
            return
        first = results[0]
        self.found.setText(f"{first['name']}  \u00b7  {first['code']}")
        self.value.setText(first.get("barcode") or first["code"])

    def _add_entry(self, name: str | None = None, price: int | None = None) -> None:
        value = self.value.text().strip()
        if not value:
            return
        fmt = self.format.currentData()
        if fmt == "ean13":
            value = barcode_gen.generate_ean13(value) if not value.isdigit() else \
                value[:12] + str(barcode_gen.ean13_check_digit(value[:12]))
        elif fmt == "ean8":
            value = value[:7] + str(barcode_gen.ean8_check_digit(value[:7]))
        self.pending.append({"value": value, "name": name or value,
                             "price_cents": price, "copies": self.copies.value()})
        self._render_list()

    def _render_list(self) -> None:
        lines = [f"{entry['copies']} \u00d7  {entry['value']}  -  {entry['name']}"
                 for entry in self.pending]
        self.list.setPlainText("\n".join(lines))

    def _clear(self) -> None:
        self.pending.clear()
        self._render_list()

    def _print(self) -> None:
        if not self.pending:
            info(self, tr("common.no_data"))
            return
        document = barcode_gen.label_sheet(
            self.services, self.pending, label_size=self.label_size.currentData(),
            fmt=self.format.currentData(), show_price=self.show_price.isChecked(),
            show_name=self.show_name.isChecked())
        dialog = PrintDialog(self.services, document, paper="a4", parent=self)
        dialog.exec()
