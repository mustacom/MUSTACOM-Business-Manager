"""Products module: catalogue grid, full editor form, import/export,
barcode generation and stock history."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget,
                               QTextEdit, QVBoxLayout)

from ...core.crud import ValidationError
from ...core.money import (cents_to_money, format_money, money_to_cents, qty_to_db,
                           db_to_qty)
from ...i18n import tr
from ..widgets.common import (DataTable, FormGrid, MoneySpin, PercentSpin, QtySpin,
                              TableModel, button, card, error, info, label, scroll, vbox)
from ..widgets.list_screen import ListScreen
from .base import BaseScreen


class ProductsScreen(ListScreen):
    module = "products"
    subtitle = tr("products.title")
    columns = [
        ("sku", tr("products.sku"), "text"),
        ("barcode", tr("products.barcode"), "text"),
        ("name", tr("products.designation"), "text"),
        ("category_name", tr("common.category"), "text"),
        ("brand_name", tr("common.brand"), "text"),
        ("purchase_price_cents", tr("products.purchase_price"), "money"),
        ("sale_price_cents", tr("products.sale_price"), "money"),
        ("vat_rate_bp", tr("products.vat"), "percent"),
        ("stock_state", tr("products.stock"), "text"),
        ("location", tr("products.location"), "text"),
        ("is_active", tr("common.active"), "bool"),
    ]

    def filter_specs(self) -> list[dict]:
        return [
            {"options": lambda: [(c["name"], c["id"]) for c in
                                 self.services.catalog.categories(kind="product")],
             "field": "category_id"},
            {"options": lambda: [(b["name"], b["id"]) for b in self.services.catalog.brands()],
             "field": "brand_id"},
            {"options": lambda: [(s["name"], s["id"]) for s in
                                 self.services.db.fetch_all("suppliers", order="name")],
             "field": "supplier_id"},
            {"options": lambda: [("OK", "ok"), (tr("dash.products_low"), "low"),
                                 (tr("dash.products_out"), "out")],
             "field": "_stock"},
        ]

    def status_columns(self) -> tuple[int, ...]:
        return ()

    def build(self) -> None:
        super().build()
        # stock column shows qty with a state suffix
        self.model.set_columns(self.columns)
        toolbar = self.toolbar_extra()
        self.root.insertWidget(1, toolbar)

    def toolbar_extra(self):
        bar = self.toolbar(
            button(tr("products.stock_history"), self._show_history, icon="\U0001F552"),
            button(tr("products.adjustment"), self._adjust_stock, icon="\u2696"),
            button(tr("products.barcode_print"), self._print_labels, icon="\U0001F3F7"),
            button(tr("products.import"), self._import, icon="\U0001F4E5"),
            stretch=True)
        return bar

    # ------------------------------------------------------------------
    def load_rows(self) -> list[dict]:
        rows, _total = self.services.catalog.products(limit=5000)
        for row in rows:
            qty = db_to_qty(row["stock"])
            state = "out" if qty <= 0 else "low" if qty <= db_to_qty(row["stock_min"]) else "ok"
            row["_stock"] = state
            row["stock_state"] = f"{qty:g}" + ("" if state == "ok" else
                                               " \u26A0" if state == "low" else " \u26D4")
        return rows

    def set_stock_filter(self, state: str) -> None:
        combos = self.filters
        if len(combos) >= 4:
            index = combos[3].findData(state)
            if index >= 0:
                combos[3].setCurrentIndex(index)
        self.refresh()

    def create_editor(self, row: dict | None) -> None:
        dialog = ProductEditor(self.services, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        self.services.catalog.delete_product(row["id"], audit=self.services.log)

    # ------------------------------------------------------------------
    def _show_history(self) -> None:
        row = self.table.selected_row()
        if not row:
            error(self, tr("products.not_found"))
            return
        dialog = StockHistoryDialog(self.services, row, parent=self)
        dialog.exec()

    def _adjust_stock(self) -> None:
        row = self.table.selected_row()
        if not row:
            return
        if not self.require("edit"):
            return
        dialog = AdjustStockDialog(self.services, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _print_labels(self) -> None:
        self.window.navigate("barcode")
        screen = self.window.screens.get("barcode")
        row = self.table.selected_row()
        if screen is not None and row and hasattr(screen, "add_product"):
            screen.add_product(row)

    def _import(self) -> None:
        if not self.require("create"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, tr("products.import"), str(self.services.paths.data),
            "Excel/CSV (*.xlsx *.csv);;Tous les fichiers (*)")
        if not path:
            return
        try:
            result = self.services.catalog.import_products(path, user_id=self.services.user_id)
        except Exception as exc:
            error(self, str(exc))
            return
        info(self, tr("products.import_result", created=result["created"],
                      updated=result["updated"], errors=result["errors"])
             + ("" if not result["error_rows"] else "\n" + "\n".join(result["error_rows"][:5])),
             tr("common.success"))
        self.refresh()

    def _export_xlsx(self) -> None:
        self._do_export("xlsx")

    def _export_csv(self) -> None:
        self._do_export("csv")

    def _do_export(self, kind: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("common.export"),
            str(self.services.paths.exports / f"produits.{kind}"), f"*.{kind}")
        if not path:
            return
        if not path.endswith(f".{kind}"):
            path += f".{kind}"
        self.services.catalog.export_products(path, term=self.search.text().strip())
        info(self, tr("print.pdf_saved", path=path), tr("common.success"))


# ---------------------------------------------------------------------------
class ProductEditor(QDialog):
    def __init__(self, services, row: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.row = row or {}
        self.setWindowTitle(tr("products.edit_product") if row else tr("products.new_product"))
        self.resize(780, 760)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # -- main tab
        main = QWidget()
        form = FormGrid(columns=2)
        self.sku = QLineEdit(self.row.get("sku", ""))
        if not self.row:
            self.sku.setPlaceholderText(self.services.catalog.generate_sku())
        form.add(tr("products.sku"), self.sku, required=True)
        self.barcode = QLineEdit(self.row.get("barcode") or "")
        gen = QPushButton("\u2699")
        gen.setToolTip(tr("products.barcode_generate"))
        gen.setFixedWidth(34)
        gen.clicked.connect(self._generate_barcode)
        barcode_row = QHBoxLayout()
        barcode_row.addWidget(self.barcode)
        barcode_row.addWidget(gen)
        wrap = QWidget()
        wrap.setLayout(barcode_row)
        form.add(tr("products.barcode"), wrap)

        self.name = QLineEdit(self.row.get("name", ""))
        form.add(tr("products.designation"), self.name, required=True)
        self.category = QComboBox()
        self.category.addItem("", None)
        for category in self.services.catalog.categories(kind="product"):
            self.category.addItem(category["name"], category["id"])
        if self.row.get("category_id"):
            self.category.setCurrentIndex(self.category.findData(self.row["category_id"]))
        form.add(tr("common.category"), self.category)
        self.subcategory = QComboBox()
        self.subcategory.addItem("", None)
        for category in self.services.catalog.categories(kind="product"):
            self.subcategory.addItem(category["name"], category["id"])
        if self.row.get("subcategory_id"):
            self.subcategory.setCurrentIndex(
                self.subcategory.findData(self.row["subcategory_id"]))
        form.add(tr("common.subcategory"), self.subcategory)
        self.brand = QComboBox()
        self.brand.setEditable(True)
        self.brand.addItem("", None)
        for brand in self.services.catalog.brands():
            self.brand.addItem(brand["name"], brand["id"])
        if self.row.get("brand_id"):
            self.brand.setCurrentIndex(self.brand.findData(self.row["brand_id"]))
        elif self.row.get("brand_name"):
            self.brand.setEditText(self.row["brand_name"])
        form.add(tr("common.brand"), self.brand)
        self.reference = QLineEdit(self.row.get("reference", ""))
        form.add(tr("products.ref"), self.reference)
        self.unit = QLineEdit(self.row.get("unit", "u"))
        form.add(tr("common.unit"), self.unit)
        self.supplier = QComboBox()
        self.supplier.addItem("", None)
        for supplier in self.services.db.fetch_all("suppliers", order="name"):
            self.supplier.addItem(supplier["name"], supplier["id"])
        if self.row.get("supplier_id"):
            self.supplier.setCurrentIndex(self.supplier.findData(self.row["supplier_id"]))
        form.add(tr("products.main_supplier"), self.supplier)
        self.location = QLineEdit(self.row.get("location", ""))
        form.add(tr("products.location"), self.location)

        self.purchase = MoneySpin()
        self.purchase.setCents(self.row.get("purchase_price_cents", 0))
        form.add(tr("products.purchase_price"), self.purchase, required=True)
        self.sale = MoneySpin()
        self.sale.setCents(self.row.get("sale_price_cents", 0))
        form.add(tr("products.sale_price"), self.sale, required=True)
        self.vat = PercentSpin()
        self.vat.setBp(self.row.get("vat_rate_bp", self.services.settings.get_float(
            "tax.default_vat_rate", 20) * 100))
        self.vat.valueChanged.connect(self._refresh_ttc)
        form.add(tr("products.vat"), self.vat)
        self.ttc = QLabel("")
        self.ttc.setObjectName("MoneyLabel")
        form.add(tr("products.price_ttc"), self.ttc)
        self._refresh_ttc()

        self.margin_button = QPushButton(tr("products.margin_pct"))
        self.margin_button.setFixedWidth(120)
        self.margin_button.clicked.connect(self._apply_margin)
        form.add(tr("products.margin"), self.margin_button)
        self.active = QCheckBox(tr("common.active"))
        self.active.setChecked(bool(self.row.get("is_active", 1)))
        form.add("", self.active)
        self.track_stock = QCheckBox(tr("products.stockable"))
        self.track_stock.setChecked(bool(self.row.get("track_stock", 1)))
        form.add("", self.track_stock)
        self.sellable = QCheckBox(tr("products.sellable"))
        self.sellable.setChecked(bool(self.row.get("sellable", 1)))
        form.add("", self.sellable)

        main.setLayout(vbox(scroll(form_widget(form)), margin=6))
        tabs.addTab(main, tr("products.form_title"))

        # -- stock tab
        stock_tab = QWidget()
        stock_form = FormGrid(columns=2)
        self.stock = QtySpin()
        self.stock.setQty(db_to_qty(self.row.get("stock", 0)))
        self.stock.setReadOnly(bool(self.row))
        stock_form.add(tr("products.stock"), self.stock)
        self.stock_min = QtySpin()
        self.stock_min.setQty(db_to_qty(self.row.get("stock_min", 0)))
        stock_form.add(tr("products.stock_min"), self.stock_min)
        self.stock_max = QtySpin()
        self.stock_max.setQty(db_to_qty(self.row.get("stock_max", 0)))
        stock_form.add(tr("products.stock_max"), self.stock_max)
        stock_tab.setLayout(vbox(scroll(form_widget(stock_form)), margin=6))
        tabs.addTab(stock_tab, tr("nav.stock"))

        # -- description tab
        self.description = QTextEdit()
        self.description.setPlainText(self.row.get("description", ""))
        tabs.addTab(self.description, tr("common.description"))

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)

    def _refresh_ttc(self) -> None:
        ht = cents_to_money(self.sale.cents())
        rate = Decimal(str(self.vat.value())) / Decimal(100)
        self.ttc.setText(format_money(ht * (1 + rate), self.services.money_symbol()))

    def _generate_barcode(self) -> None:
        from ...core.barcode_gen import generate_ean13

        seed = self.sku.text() or self.services.catalog.generate_sku()
        self.barcode.setText(generate_ean13(seed))

    def _apply_margin(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        value, ok = QInputDialog.getDouble(self, tr("products.margin_pct"),
                                           tr("products.margin_pct"), 30.0, 0, 500, 2)
        if not ok:
            return
        cost = cents_to_money(self.purchase.cents())
        target = cost / (1 - Decimal(str(value)) / 100) if value < 100 else cost * 2
        self.sale.setValue(float(target))

    def _save(self) -> None:
        brand_id = self.brand.currentData()
        if brand_id is None and self.brand.currentText().strip():
            brand_id = self.services.catalog.save_brand(self.brand.currentText().strip())
        data = {
            "sku": self.sku.text().strip() or self.services.catalog.generate_sku(),
            "barcode": self.barcode.text().strip(),
            "name": self.name.text().strip(),
            "category_id": self.category.currentData(),
            "subcategory_id": self.subcategory.currentData(),
            "brand_id": brand_id,
            "reference": self.reference.text().strip(),
            "unit": self.unit.text().strip() or "u",
            "supplier_id": self.supplier.currentData(),
            "location": self.location.text().strip(),
            "purchase_price_cents": self.purchase.cents(),
            "sale_price_cents": self.sale.cents(),
            "vat_rate_bp": self.vat.bp(),
            "stock": self.stock.qty() if not self.row else db_to_qty(self.row.get("stock", 0)),
            "stock_min": self.stock_min.qty(),
            "stock_max": self.stock_max.qty(),
            "description": self.description.toPlainText(),
            "is_active": self.active.isChecked(),
            "track_stock": self.track_stock.isChecked(),
            "sellable": self.sellable.isChecked(),
        }
        try:
            self.services.catalog.save_product(data, product_id=self.row.get("id"),
                                               user_id=self.services.user_id,
                                               audit=self.services.log)
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.services.log("product.save", entity_type="product", details=data["sku"])
        self.accept()


def form_widget(form: FormGrid):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.addWidget(form)
    layout.addStretch(1)
    return widget


# ---------------------------------------------------------------------------
class StockHistoryDialog(QDialog):
    def __init__(self, services, product: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self.setWindowTitle(f"{tr('products.stock_history')} - {product['name']}")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        head = QLabel(f"{product['sku']}  \u00b7  {tr('products.stock')} : "
                      f"{db_to_qty(product['stock']):g}")
        head.setStyleSheet("font-weight:700")
        layout.addWidget(head)
        model = TableModel([
            ("date", tr("common.date"), "datetime"),
            ("movement_type", tr("stock.movement_type"), "movement"),
            ("quantity", tr("stock.delta"), "qty"),
            ("qty_before", tr("stock.qty_before"), "qty"),
            ("qty_after", tr("stock.qty_after"), "qty"),
            ("ref_number", tr("common.reference"), "text"),
            ("username", tr("audit.user"), "text"),
            ("reason", tr("stock.reason"), "text"),
        ])
        table = DataTable(model)
        model.set_rows(self.services.stock.movements(product["id"], limit=1000))
        layout.addWidget(table, 1)
        layout.addWidget(button(tr("common.close"), self.reject))


class AdjustStockDialog(QDialog):
    def __init__(self, services, product: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self.setWindowTitle(f"{tr('products.adjustment')} - {product['name']}")
        self.resize(460, 300)
        layout = QVBoxLayout(self)
        form = FormGrid(columns=1)
        self.current = QLabel(f"{db_to_qty(product['stock']):g}")
        form.add(tr("products.stock"), self.current)
        self.target = QtySpin()
        self.target.setQty(db_to_qty(product["stock"]))
        form.add(tr("stock.qty_after"), self.target)
        self.reason = QLineEdit()
        form.add(tr("stock.reason"), self.reason)
        layout.addWidget(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        layout.addLayout(actions)

    def _save(self) -> None:
        try:
            self.services.stock.set_stock(
                self.product["id"], self.target.qty(), "adjustment",
                reason=self.reason.text().strip() or "Ajustement manuel",
                user_id=self.services.user_id)
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.log("stock.adjustment", entity_type="product",
                          entity_id=self.product["id"],
                          details=f"{self.product['sku']} -> {self.target.qty()}")
        self.accept()
