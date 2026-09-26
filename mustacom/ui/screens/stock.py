"""Stock & inventory: movements journal, adjustments, transfers, physical
inventory count and stock reports."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout,
                               QHBoxLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget)

from ...core.money import cents_to_money

from ...core.money import db_to_qty, format_money
from ...i18n import tr
from ...reporting.exporters import export_rows
from ..widgets.common import (DataTable, FormGrid, QtySpin, TableModel, button, card,
                              confirm, error, info, label, vbox)
from .base import BaseScreen


class StockScreen(BaseScreen):
    module = "stock"
    subtitle = tr("stock.title")

    def build(self) -> None:
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)

        # -- movements
        movements = QWidget()
        layout = QVBoxLayout(movements)
        bar = QHBoxLayout()
        self.movement_type = QComboBox()
        self.movement_type.addItem(tr("common.all"), "")
        for code in ("purchase", "sale", "return_client", "return_supplier",
                     "adjustment", "transfer", "damage", "loss", "inventory", "initial"):
            self.movement_type.addItem(tr(f"mov.{code}"), code)
        self.movement_type.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.movement_type)
        self.product_filter = QLineEdit()
        self.product_filter.setPlaceholderText(tr("pos.search_product"))
        self.product_filter.returnPressed.connect(self.refresh)
        bar.addWidget(self.product_filter)
        bar.addWidget(button(tr("products.adjustment"), self._adjust, icon="\u2696"))
        bar.addWidget(button(tr("stock.transfer"), self._transfer, icon="\u21C4"))
        bar.addWidget(button(tr("stock.damage"), self._damage, icon="\u26A0"))
        bar.addWidget(button(tr("common.export_csv"), self._export_movements))
        bar.addStretch(1)
        layout.addLayout(bar)
        self.mov_model = TableModel([
            ("date", tr("common.date"), "datetime"),
            ("sku", tr("products.sku"), "text"),
            ("product_name", tr("products.designation"), "text"),
            ("movement_type", tr("stock.movement_type"), "movement"),
            ("quantity", tr("stock.delta"), "qty"),
            ("qty_before", tr("stock.qty_before"), "qty"),
            ("qty_after", tr("stock.qty_after"), "qty"),
            ("location_from", tr("stock.from_location"), "text"),
            ("location_to", tr("stock.to_location"), "text"),
            ("ref_number", tr("common.reference"), "text"),
            ("username", tr("audit.user"), "text"),
        ])
        self.mov_table = DataTable(self.mov_model)
        layout.addWidget(self.mov_table, 1)
        self.tabs.addTab(movements, tr("stock.movements"))

        # -- valuation
        valuation = QWidget()
        val_layout = QVBoxLayout(valuation)
        self.valuation_card = card(tr("stock.report_valuation"))
        self.valuation_body = self.valuation_card.layout()
        val_layout.addWidget(self.valuation_card)
        self.val_model = TableModel([
            ("sku", tr("products.sku"), "text"),
            ("name", tr("products.designation"), "text"),
            ("stock", "Qt\u00e9", "text"),
            ("purchase_price_cents", tr("products.purchase_price"), "money"),
            ("value_ht", tr("products.value_ht"), "amount"),
            ("value_ttc", tr("products.value_ttc"), "amount"),
        ])
        self.val_table = DataTable(self.val_model)
        val_layout.addWidget(self.val_table, 1)
        val_layout.addWidget(button(tr("common.export_excel"), self._export_valuation))
        self.tabs.addTab(valuation, tr("stock.report_valuation"))

        # -- reports (low / out)
        reports = QWidget()
        rep_layout = QVBoxLayout(reports)
        self.low_model = TableModel([
            ("sku", tr("products.sku"), "text"),
            ("name", tr("products.designation"), "text"),
            ("stock", tr("products.stock"), "text"),
            ("stock_min", tr("products.stock_min"), "text"),
            ("supplier_name", tr("products.main_supplier"), "text"),
        ])
        self.low_table = DataTable(self.low_model)
        self.out_table = DataTable(TableModel(self.low_model._columns))
        rep_layout.addWidget(label(tr("stock.report_low"), "CardTitle"))
        rep_layout.addWidget(self.low_table, 1)
        rep_layout.addWidget(label(tr("stock.report_out"), "CardTitle"))
        rep_layout.addWidget(self.out_table, 1)
        self.tabs.addTab(reports, tr("stock.report_low"))

        # -- inventory count
        inventory = QWidget()
        inv_layout = QVBoxLayout(inventory)
        inv_bar = QHBoxLayout()
        inv_bar.addWidget(button(tr("stock.count"), self._start_count, kind="primary",
                                 icon="\U0001F4CB"))
        self.inv_combo = QComboBox()
        self.inv_combo.setMinimumWidth(260)
        self.inv_combo.currentIndexChanged.connect(self._load_count)
        inv_bar.addWidget(self.inv_combo, 1)
        inv_bar.addWidget(button(tr("stock.apply_count"), self._apply_count, kind="success"))
        inv_layout.addLayout(inv_bar)
        self.count_model = TableModel([
            ("sku", tr("products.sku"), "text"),
            ("name", tr("products.designation"), "text"),
            ("expected_qty", tr("stock.qty_before"), "qty"),
            ("counted_qty", tr("stock.counted"), "qty"),
            ("difference", tr("stock.delta"), "qty"),
        ])
        self.count_table = DataTable(self.count_model)
        self.count_table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.count_table.model_.set_rows([])
        inv_layout.addWidget(self.count_table, 1)
        self.tabs.addTab(inventory, tr("stock.count"))
        super().build()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if not self._built:
            return
        self.mov_model.symbol = self.services.money_symbol()
        self.val_model.symbol = self.services.money_symbol()
        movement_type = self.movement_type.currentData() or ""
        term = self.product_filter.text().strip().lower()
        rows = self.services.stock.movements(limit=2000, movement_type=movement_type)
        if term:
            rows = [r for r in rows if term in (r.get("product_name", "") + r.get("sku", "")).lower()]
        self.mov_model.set_rows(rows)

        valuation = self.services.stock.valuation()
        self._render_valuation(valuation)
        products, _ = self.services.catalog.products(limit=10000)
        value_rows = []
        for product in products:
            qty = db_to_qty(product["stock"])
            if qty <= 0:
                continue
            value_rows.append({
                **product,
                "stock": f"{qty:g}",
                "value_ht": qty * Decimal(product["purchase_price_cents"]) / 100,
                "value_ttc": qty * Decimal(product["purchase_price_cents"]) / 100 *
                    (1 + Decimal(product["vat_rate_bp"]) / 10000),
            })
        self.val_model.set_rows(value_rows)

        low = self.services.stock.low_stock()
        for row in low:
            row["stock"] = f"{db_to_qty(row['stock']):g}"
            row["stock_min"] = f"{db_to_qty(row['stock_min']):g}"
        self.low_model.set_rows(low)
        out = self.services.stock.low_stock(only_out=True)
        for row in out:
            row["stock"] = f"{db_to_qty(row['stock']):g}"
            row["stock_min"] = f"{db_to_qty(row['stock_min']):g}"
        self.out_table.model_.set_rows(out)

        self.inv_combo.blockSignals(True)
        current = self.inv_combo.currentData()
        self.inv_combo.clear()
        for inventory_row in self.services.db.fetch_all("inventories", order="id DESC"):
            self.inv_combo.addItem(
                f"{inventory_row['number']}  ({tr(f'status.{inventory_row['status']}', )})",
                inventory_row["id"])
        if current:
            index = self.inv_combo.findData(current)
            if index >= 0:
                self.inv_combo.setCurrentIndex(index)
        self.inv_combo.blockSignals(False)
        self._load_count()

    def _render_valuation(self, valuation: dict) -> None:
        body = self.valuation_body
        while body.count() > 1:
            item = body.takeAt(body.count() - 1)
            if item.widget():
                item.widget().deleteLater()
        symbol = self.services.money_symbol()
        money = lambda cents: format_money(cents_to_money(cents), symbol)  # noqa: E731
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.addWidget(label(
            f"{tr('products.value_ht')} : <b>{money(valuation['value_purchase'])}</b>",
            "MoneyLabel"))
        holder_layout.addWidget(label(
            f"{tr('products.value_ttc')} : <b>{money(valuation['value_sale'])}</b>",
            "MoneyLabel"))
        holder_layout.addWidget(label(
            f"{tr('dash.products_stock')} : {valuation['in_stock']}  |  "
            f"{tr('dash.products_low')} : {valuation['low']}  |  "
            f"{tr('dash.products_out')} : {valuation['out_of_stock']}"))
        body.addWidget(holder)

    # ------------------------------------------------------------------
    def _adjust(self) -> None:
        from .products import AdjustStockDialog

        dialog = ProductPick(self.services, self)
        if dialog.exec() != QDialog.Accepted:
            return
        adjust = AdjustStockDialog(self.services, dialog.product, parent=self)
        if adjust.exec() == QDialog.Accepted:
            self.refresh()

    def _transfer(self) -> None:
        dialog = ProductPick(self.services, self)
        if dialog.exec() != QDialog.Accepted:
            return
        editor = TransferDialog(self.services, dialog.product, parent=self)
        if editor.exec() == QDialog.Accepted:
            self.refresh()

    def _damage(self) -> None:
        dialog = ProductPick(self.services, self)
        if dialog.exec() != QDialog.Accepted:
            return
        editor = DamageDialog(self.services, dialog.product, parent=self)
        if editor.exec() == QDialog.Accepted:
            self.refresh()

    def _export_movements(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self, tr("common.export_csv"),
                                              str(self.services.paths.exports /
                                                  "mouvements-stock.csv"), "*.csv")
        if path:
            export_rows(path, self.mov_model._columns, self.mov_model.rows)

    def _export_valuation(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self, tr("common.export_excel"),
                                              str(self.services.paths.exports /
                                                  "valorisation.xlsx"), "*.xlsx")
        if path:
            export_rows(path, self.val_model._columns, self.val_model.rows)

    # -- inventory count ------------------------------------------------
    def _start_count(self) -> None:
        if not self.require("create"):
            return
        inventory = self.services.stock.start_inventory(user_id=self.services.user_id,
                                                        numbering=self.services.numbering)
        self.services.log("stock.inventory_start", entity_type="inventory",
                          entity_id=inventory["id"], details=inventory["number"])
        self.refresh()
        self.inv_combo.setCurrentIndex(self.inv_combo.findData(inventory["id"]))

    def _load_count(self) -> None:
        inventory_id = self.inv_combo.currentData()
        if not inventory_id:
            self.count_model.set_rows([])
            return
        rows = self.services.stock.inventory_items(inventory_id)
        self.count_model.set_rows(rows)

    def _apply_count(self) -> None:
        inventory_id = self.inv_combo.currentData()
        if not inventory_id:
            return
        if not self.require("validate"):
            return
        # ask counted qty for each row with a dialog-less flow: double click edits
        applied = self.services.stock.apply_inventory(
            inventory_id, user_id=self.services.user_id)
        self.services.log("stock.inventory_apply", entity_type="inventory",
                          entity_id=inventory_id, details=f"{applied} lignes")
        info(self, tr("common.saved_ok"), tr("common.success"))
        self.refresh()


class ProductPick(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.product: dict | None = None
        self.setWindowTitle(tr("common.select"))
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("pos.search_product"))
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.model = TableModel([("sku", "SKU", "text"), ("name", "Nom", "text"),
                                 ("stock", "Stock", "text")])
        self.table = DataTable(self.model)
        self.table.doubleClickedRow.connect(self._pick)
        layout.addWidget(self.table, 1)
        layout.addWidget(button(tr("common.select"), self._pick_selected, kind="primary"))
        self._filter("")

    def _filter(self, term: str) -> None:
        rows, _ = self.services.catalog.products(term=term, limit=100)
        for row in rows:
            row["stock"] = f"{db_to_qty(row['stock']):g}"
        self.model.set_rows(rows)

    def _pick(self, row: dict) -> None:
        self.product = self.services.catalog.product(row["id"])
        self.accept()

    def _pick_selected(self) -> None:
        row = self.table.selected_row()
        if row:
            self._pick(row)


class TransferDialog(QDialog):
    def __init__(self, services, product: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self.setWindowTitle(f"{tr('stock.transfer')} - {product['name']}")
        self.resize(420, 240)
        form = QFormLayout(self)
        self.quantity = QtySpin()
        form.addRow(tr("common.quantity"), self.quantity)
        self.source = QLineEdit(product.get("location", ""))
        form.addRow(tr("stock.from_location"), self.source)
        self.destination = QLineEdit()
        form.addRow(tr("stock.to_location"), self.destination)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(button(tr("common.cancel"), self.reject))
        bar.addWidget(button(tr("common.save"), self._save, kind="primary"))
        form.addRow(bar)

    def _save(self) -> None:
        try:
            self.services.stock.transfer(self.product["id"], self.quantity.qty(),
                                         self.source.text().strip(),
                                         self.destination.text().strip(),
                                         user_id=self.services.user_id)
        except Exception as exc:
            error(self, str(exc))
            return
        self.accept()


class DamageDialog(QDialog):
    def __init__(self, services, product: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self.setWindowTitle(f"{tr('stock.damage')} - {product['name']}")
        self.resize(420, 240)
        form = QFormLayout(self)
        self.quantity = QtySpin()
        form.addRow(tr("common.quantity"), self.quantity)
        self.kind = QComboBox()
        self.kind.addItem(tr("stock.damage"), "damage")
        self.kind.addItem(tr("stock.loss"), "loss")
        form.addRow(tr("common.type"), self.kind)
        self.reason = QLineEdit()
        form.addRow(tr("stock.reason"), self.reason)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(button(tr("common.cancel"), self.reject))
        bar.addWidget(button(tr("common.save"), self._save, kind="danger"))
        form.addRow(bar)

    def _save(self) -> None:
        try:
            self.services.stock.move(self.product["id"], -self.quantity.qty(),
                                     self.kind.currentData(),
                                     reason=self.reason.text().strip(),
                                     user_id=self.services.user_id)
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.log("stock.damage", entity_type="product",
                          entity_id=self.product["id"],
                          details=f"{self.product['sku']} -{self.quantity.qty()}")
        self.accept()
