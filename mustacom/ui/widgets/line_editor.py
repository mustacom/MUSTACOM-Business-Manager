"""Editable sales-line grid shared by POS, devis, commandes and factures.

The editor keeps a list of :class:`CartItem`, displays them in a table where
quantity / price / discount can be tweaked with inline spinners, and emits
``linesChanged`` so the parent can recompute totals.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHBoxLayout,
                               QHeaderView, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ...core.money import (cents_to_money, compute_totals, format_money, money_to_cents,
                           to_decimal)
from ...core.sales import CartItem, cart_lines
from ...i18n import tr

COLUMNS = ("code", "label", "qty", "unit_price", "discount", "vat", "total", "actions")


class LineEditor(QWidget):
    linesChanged = Signal()

    def __init__(self, services, parent=None, readonly: bool = False):
        super().__init__(parent)
        self.services = services
        self.readonly = readonly
        self.items: list[CartItem] = []
        self.symbol = services.money_symbol()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([
            tr("common.code"), tr("common.label"), tr("common.quantity"),
            tr("common.unit_price"), tr("pos.discount"), tr("products.vat"),
            tr("common.total"), tr("common.actions")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(48)
        self.table.setMinimumWidth(430)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(220)
        layout.addWidget(self.table, 1)

        if not readonly:
            bar = QHBoxLayout()
            remove = QPushButton(tr("common.delete"))
            remove.clicked.connect(self.remove_selected)
            bar.addStretch(1)
            bar.addWidget(remove)
            layout.addLayout(bar)

        self.table.cellChanged.connect(self._on_cell_changed)

    # ------------------------------------------------------------------
    def add_item(self, item: CartItem) -> None:
        for existing in self.items:
            if (existing.ref_type == item.ref_type and existing.ref_id == item.ref_id
                    and existing.unit_price_cents == item.unit_price_cents):
                existing.qty = to_decimal(existing.qty) + to_decimal(item.qty)
                self.rebuild()
                return
        self.items.append(item)
        self.rebuild()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.items):
                del self.items[row]
        self.rebuild()

    def clear(self) -> None:
        self.items.clear()
        self.rebuild()

    def totals(self, global_percent=0, global_fixed=0) -> dict:
        return compute_totals(cart_lines(self.items), to_decimal(global_percent),
                              to_decimal(global_fixed))

    # ------------------------------------------------------------------
    def rebuild(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.items))
        totals = self.totals()
        prorated = totals.get("prorated_discount", {})
        for row, item in enumerate(self.items):
            line = item.to_line()
            net = line.net_ht - prorated.get(row, Decimal(0))
            vat = (net * line.vat_rate / Decimal(100)).quantize(Decimal("0.01"))
            self._text(row, 0, item.code)
            self._text(row, 1, item.label)
            qty = QDoubleSpinBox()
            qty.setDecimals(3)
            qty.setRange(0.001, 999999)
            qty.setValue(float(to_decimal(item.qty)))
            qty.setSuffix(f" {item.unit}")
            qty.valueChanged.connect(lambda value, r=row: self._update_qty(r, value))
            self.table.setCellWidget(row, 2, qty)
            price = QDoubleSpinBox()
            price.setDecimals(2)
            price.setRange(0, 99999999)
            price.setSuffix(f" {self.symbol}")
            price.setValue(float(cents_to_money(item.unit_price_cents)))
            price.setReadOnly(self.readonly)
            price.valueChanged.connect(lambda value, r=row: self._update_price(r, value))
            self.table.setCellWidget(row, 3, price)
            discount = QDoubleSpinBox()
            discount.setDecimals(2)
            discount.setRange(0, 100)
            discount.setSuffix(" %")
            discount.setValue(float(Decimal(item.discount_percent_bp) / 100))
            discount.setReadOnly(self.readonly)
            discount.valueChanged.connect(lambda value, r=row: self._update_discount(r, value))
            self.table.setCellWidget(row, 4, discount)
            self._text(row, 5, f"{Decimal(item.vat_rate_bp) / 100:g} %")
            self._text(row, 6, format_money(net + vat, self.symbol))
            if not self.readonly:
                remove = QPushButton("\u2715")
                remove.setFixedWidth(30)
                remove.clicked.connect(lambda _c, r=row: self._remove_row(r))
                self.table.setCellWidget(row, 7, remove)
        self.table.blockSignals(False)
        self.linesChanged.emit()

    def _text(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        if column in (5, 6):
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, column, item)

    def _remove_row(self, row: int) -> None:
        if 0 <= row < len(self.items):
            del self.items[row]
            self.rebuild()

    def _update_qty(self, row: int, value: float) -> None:
        if 0 <= row < len(self.items):
            self.items[row].qty = Decimal(str(value))
            self._refresh_totals()

    def _update_price(self, row: int, value: float) -> None:
        if 0 <= row < len(self.items):
            self.items[row].unit_price_cents = money_to_cents(value)
            self._refresh_totals()

    def _update_discount(self, row: int, value: float) -> None:
        if 0 <= row < len(self.items):
            self.items[row].discount_percent_bp = int(round(value * 100))
            self._refresh_totals()

    def _refresh_totals(self) -> None:
        totals = self.totals()
        prorated = totals.get("prorated_discount", {})
        self.table.blockSignals(True)
        for row, item in enumerate(self.items):
            line = item.to_line()
            net = line.net_ht - prorated.get(row, Decimal(0))
            vat = (net * line.vat_rate / Decimal(100)).quantize(Decimal("0.01"))
            self._text(row, 6, format_money(net + vat, self.symbol))
        self.table.blockSignals(False)
        self.linesChanged.emit()

    def _on_cell_changed(self, _row: int, _column: int) -> None:
        pass
