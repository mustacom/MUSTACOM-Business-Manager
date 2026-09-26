"""Point of sale: scanner box, product search, cart, discounts, payments,
held sales, returns.  Keyboard shortcuts: F2 search, F4 customer, F8 payment,
F9 hold, F12 validate, Esc cancel."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from ...core.money import cents_to_money, format_money, money_to_cents, to_decimal
from ...core.sales import CartItem
from ...core.stock import StockError
from ...i18n import tr
from ...reporting import render
from ..dialogs.print_dialog import PrintDialog
from ..widgets.common import (DataTable, MoneySpin, PercentSpin, TableModel, button,
                              card, error, info, label, vbox)
from ..widgets.line_editor import LineEditor
from .base import BaseScreen

PAYMENT_METHODS = (
    ("cash", "pay.cash"), ("card", "pay.card"), ("transfer", "pay.transfer"),
    ("check", "pay.check"), ("credit", "pay.credit"), ("mixed", "pay.mixed"),
)


class PosScreen(BaseScreen):
    module = "pos"
    subtitle = tr("pos.title")

    def build(self) -> None:
        body = QHBoxLayout()
        body.setSpacing(10)
        body.addLayout(self._build_left(), 3)
        body.addLayout(self._build_right(), 2)
        self.root.addLayout(body, 1)
        self._setup_shortcuts()
        super().build()

    # ------------------------------------------------------------------
    def _build_left(self) -> QVBoxLayout:
        left = QVBoxLayout()
        left.setSpacing(8)

        scan_row = QHBoxLayout()
        self.scan_box = QLineEdit()
        self.scan_box.setPlaceholderText(tr("pos.scan") + "  (Entr\u00e9e)")
        self.scan_box.returnPressed.connect(self._on_scan)
        scan_row.addWidget(self.scan_box, 2)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("pos.search_product"))
        self.search_box.textChanged.connect(self._render_results)
        scan_row.addWidget(self.search_box, 2)
        left.addLayout(scan_row)

        self.results = QListWidget()
        self.results.setMaximumHeight(150)
        self.results.itemDoubleClicked.connect(self._add_result)
        left.addWidget(self.results)

        self.editor = LineEditor(self.services)
        self.editor.linesChanged.connect(self._update_totals)
        left.addWidget(self.editor, 1)
        return left

    def _build_right(self) -> QVBoxLayout:
        right = QVBoxLayout()
        right.setSpacing(8)

        customer_card = QFrame()
        customer_card.setObjectName("Card")
        customer_layout = QVBoxLayout(customer_card)
        customer_layout.addWidget(label(tr("pos.customer"), "FormLabel"))
        row = QHBoxLayout()
        self.customer_box = QComboBox()
        self.customer_box.setMinimumWidth(150)
        row.addWidget(self.customer_box, 1)
        refresh = QPushButton("\u21BB")
        refresh.setFixedWidth(34)
        refresh.clicked.connect(self._load_customers)
        row.addWidget(refresh)
        customer_layout.addLayout(row)
        right.addWidget(customer_card)

        discount_card = QFrame()
        discount_card.setObjectName("Card")
        discount_layout = QGridLayout(discount_card)
        discount_layout.setContentsMargins(8, 6, 8, 6)
        self.discount_percent = PercentSpin()
        self.discount_percent.valueChanged.connect(self._update_totals)
        self.discount_fixed = MoneySpin()
        self.discount_fixed.valueChanged.connect(self._update_totals)
        discount_layout.addWidget(label(tr("pos.discount_percent") + " :"), 0, 0)
        discount_layout.addWidget(self.discount_percent, 0, 1)
        discount_layout.addWidget(label(tr("pos.discount_amount") + " :"), 1, 0)
        discount_layout.addWidget(self.discount_fixed, 1, 1)
        right.addWidget(discount_card)

        totals = QFrame()
        totals.setObjectName("PosTotalBox")
        totals_layout = QVBoxLayout(totals)
        self.total_ht_label = QLabel("0,00")
        self.total_ht_label.setObjectName("MoneyLabel")
        self.total_vat_label = QLabel("0,00")
        self.total_ttc_label = QLabel("0,00")
        self.total_ttc_label.setObjectName("PosTotalValue")
        for name, widget in ((tr("pos.total_ht"), self.total_ht_label),
                             (tr("pos.total_vat"), self.total_vat_label),
                             (tr("pos.total_ttc"), self.total_ttc_label)):
            row = QHBoxLayout()
            row.addWidget(QLabel(name + " :"))
            row.addStretch(1)
            row.addWidget(widget)
            totals_layout.addLayout(row)
        right.addWidget(totals)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        pay = QPushButton(tr("pos.payment"))
        pay.setObjectName("PrimaryButton")
        pay.clicked.connect(self._open_payment)
        actions.addWidget(pay)
        row = QHBoxLayout()
        row.addWidget(button(tr("pos.hold"), self._hold_sale, icon="\u23F8"))
        row.addWidget(button(tr("pos.resume"), self._resume_sale, icon="\u25B6"))
        actions.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button(tr("pos.return_mode"), self._return_mode, icon="\u21A9"))
        row.addWidget(button(tr("pos.cancel_sale"), self._cancel_sale, kind="danger",
                             icon="\u2716"))
        actions.addLayout(row)
        right.addLayout(actions)

        hint = QLabel("F2: recherche  |  F4: client  |  F8/F12: paiement  |  "
                      "F9: attente  |  \u21A9: retour/avoir  |  Esc: annuler")
        hint.setObjectName("PosKeyHint")
        hint.setWordWrap(True)
        right.addWidget(hint)
        right.addStretch(1)
        return right

    def _setup_shortcuts(self) -> None:
        for key, slot in (("F2", lambda: self.search_box.setFocus()),
                          ("F4", lambda: self.customer_box.showPopup()),
                          ("F8", self._open_payment),
                          ("F9", self._hold_sale),
                          ("F12", self._open_payment),
                          ("Esc", self._cancel_sale)):
            shortcut = QPushButton(self)
            shortcut.hide()
            shortcut.setShortcut(QKeySequence(key))
            shortcut.clicked.connect(slot)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if not self._built:
            return
        self._load_customers()
        self.editor.symbol = self.services.money_symbol()
        self._update_totals()

    def _load_customers(self) -> None:
        current = self.customer_box.currentData()
        self.customer_box.clear()
        self.customer_box.addItem(tr("pos.anonymous"), None)
        for customer in self.services.catalog.parties("customers"):
            self.customer_box.addItem(customer["name"], customer["id"])
        if current:
            index = self.customer_box.findData(current)
            if index >= 0:
                self.customer_box.setCurrentIndex(index)

    def _on_scan(self) -> None:
        code = self.scan_box.text().strip()
        self.scan_box.clear()
        if not code:
            return
        item = self.services.sales.find_by_code(code)
        if item is None:
            results = self.services.sales.search(code, limit=1)
            if results:
                first = results[0]
                product = (self.services.db.fetch("products", first["id"])
                           if first["kind"] == "product" else None)
                service = (self.services.db.fetch("services", first["id"])
                           if first["kind"] == "service" else None)
                item = CartItem.from_product(product) if product else \
                    CartItem.from_service(service)
        if item is None:
            error(self, tr("products.not_found"))
            return
        self.editor.add_item(item)
        self.scan_box.setFocus()

    def _render_results(self, term: str) -> None:
        self.results.clear()
        if not term.strip():
            return
        for row in self.services.sales.search(term, limit=25):
            stock = ""
            if row["kind"] == "product":
                stock = f"  [stock {row['stock'] / 1000:g}]"
            item = QListWidgetItem(
                f"{row['name']}  -  {format_money(cents_to_money(row['price_cents']), self.services.money_symbol())}{stock}")
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)

    def _add_result(self, list_item: QListWidgetItem) -> None:
        row = list_item.data(Qt.UserRole)
        source = self.services.db.fetch("products" if row["kind"] == "product"
                                        else "services", row["id"])
        item = CartItem.from_product(source) if row["kind"] == "product" else \
            CartItem.from_service(source)
        self.editor.add_item(item)

    def _update_totals(self) -> None:
        totals = self.editor.totals(self.discount_percent.value(),
                                    cents_to_money(self.discount_fixed.cents()))
        symbol = self.services.money_symbol()
        self.total_ht_label.setText(format_money(totals["total_ht"], symbol))
        self.total_vat_label.setText(format_money(totals["total_vat"], symbol))
        self.total_ttc_label.setText(format_money(totals["total_ttc"], symbol))
        self._last_totals = totals

    # ------------------------------------------------------------------
    def _cancel_sale(self) -> None:
        self.editor.clear()
        self.discount_percent.setValue(0)
        self.discount_fixed.setValue(0)

    def _hold_sale(self) -> None:
        if not self.editor.items:
            return
        self.services.sales.hold(self.editor.items, self.customer_box.currentData(),
                                 cash_session_id=self._session_id(),
                                 user_id=self.services.user_id)
        self._cancel_sale()
        info(self, tr("pos.hold_ok"), tr("common.success"))

    def _resume_sale(self) -> None:
        held = self.services.sales.held_list(self._session_id())
        if not held:
            info(self, tr("common.no_data"))
            return
        dialog = HeldSalesDialog(self.services, held, parent=self)
        if dialog.exec() != QDialog.Accepted or not dialog.result:
            return
        self.editor.items = dialog.result["items"]
        if dialog.result.get("customer_id"):
            index = self.customer_box.findData(dialog.result["customer_id"])
            if index >= 0:
                self.customer_box.setCurrentIndex(index)
        self.discount_percent.setValue(dialog.result.get("discount_percent_bp", 0) / 100)
        self.discount_fixed.setCents(dialog.result.get("discount_cents", 0))
        self.editor.rebuild()

    def _session_id(self) -> int | None:
        session = self.services.cash.current_session()
        return session.get("id") if session else None

    def _return_mode(self) -> None:
        dialog = ReturnDialog(self.services, parent=self)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            info(self, tr("common.success"), tr("pos.refund"))
            self.notify_change()

    # ------------------------------------------------------------------
    def _open_payment(self) -> None:
        if not self.editor.items:
            error(self, tr("pos.empty_cart"))
            return
        require_session = self.services.settings.get_bool("pos.require_cash_session", True)
        session = self.services.cash.current_session()
        if require_session and not session:
            error(self, tr("pos.no_cash_session"))
            self.window.navigate("cash")
            return
        totals = self.editor.totals(self.discount_percent.value(),
                                    cents_to_money(self.discount_fixed.cents()))
        dialog = PaymentDialog(self.services, totals["total_ttc_cents"],
                               customer_id=self.customer_box.currentData(), parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._validate(dialog.payments, dialog.method, dialog.received_cents)

    def _validate(self, payments: list[dict], method: str, received: int) -> None:
        totals = self.editor.totals(self.discount_percent.value(),
                                    cents_to_money(self.discount_fixed.cents()))
        allow_negative = self.services.settings.get_bool("pos.allow_negative_stock", False)
        try:
            sale = self.services.sales.validate_sale(
                self.editor.items,
                customer_id=self.customer_box.currentData(),
                payment_method=method,
                payments=payments,
                amount_received_cents=received,
                discount_percent_bp=int(self.discount_percent.value() * 100),
                discount_cents=self.discount_fixed.cents(),
                cash_session_id=self._session_id(),
                user_id=self.services.user_id,
                allow_negative_stock=allow_negative,
                audit=self.services.log)
        except (StockError, ValueError) as exc:
            error(self, str(exc))
            return
        self.services.log("pos.sale", entity_type="sale", entity_id=sale["id"],
                          details=f"{sale['number']} {totals['total_ttc_cents']/100}")
        receipt = ReceiptDialog(self.services, sale, parent=self)
        receipt.exec()
        self._cancel_sale()
        self.notify_change()


class PaymentDialog(QDialog):
    def __init__(self, services, total_cents: int, customer_id: int | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.total_cents = total_cents
        self.customer_id = customer_id
        self.payments: list[dict] = []
        self.method = "cash"
        self.received_cents = total_cents
        self.setWindowTitle(tr("pos.payment"))
        self.resize(560, 520)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        amount = QLabel(format_money(cents_to_money(self.total_cents),
                                     self.services.money_symbol()))
        amount.setObjectName("PosTotalValue")
        amount.setStyleSheet("color:#0F766E")
        caption = QLabel(tr("pos.amount_due"))
        caption.setObjectName("FormLabel")
        layout.addWidget(caption)
        layout.addWidget(amount)

        form = QFormLayout()
        self.method_box = QComboBox()
        for code, key in PAYMENT_METHODS:
            self.method_box.addItem(tr(key), code)
        self.method_box.currentIndexChanged.connect(self._on_method)
        form.addRow(tr("pay.method"), self.method_box)
        self.received = MoneySpin()
        self.received.setCents(self.total_cents)
        self.received.valueChanged.connect(self._on_received)
        form.addRow(tr("pos.amount_received"), self.received)
        self.change_label = QLabel("0,00")
        self.change_label.setObjectName("MoneyLabel")
        form.addRow(tr("pos.change"), self.change_label)
        layout.addLayout(form)

        self.split_box = QWidget()
        split_layout = QVBoxLayout(self.split_box)
        split_layout.setContentsMargins(0, 0, 0, 0)
        self.split_model = TableModel([
            ("method", tr("pay.method"), "payment"),
            ("amount_cents", tr("common.amount"), "money"),
        ])
        self.split_table = DataTable(self.split_model)
        split_layout.addWidget(self.split_table)
        row = QHBoxLayout()
        self.split_method = QComboBox()
        for code, key in PAYMENT_METHODS[:-2]:
            self.split_method.addItem(tr(key), code)
        row.addWidget(self.split_method)
        self.split_amount = MoneySpin()
        row.addWidget(self.split_amount)
        row.addWidget(button(tr("common.add"), self._add_split, kind="primary"))
        split_layout.addLayout(row)
        self.split_box.hide()
        layout.addWidget(self.split_box)

        if self.customer_id:
            available = self.services.parties.customer_credit_available(self.customer_id)
            if available:
                layout.addWidget(label(
                    f"{tr('customers.credit_available')} : "
                    f"{format_money(cents_to_money(available), self.services.money_symbol())}",
                    "HintLabel"))

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        validate = QPushButton(tr("common.validate"))
        validate.setObjectName("PrimaryButton")
        validate.clicked.connect(self._validate)
        actions.addWidget(validate)
        layout.addLayout(actions)

    def _on_method(self) -> None:
        self.method = self.method_box.currentData()
        self.split_box.setVisible(self.method == "mixed")
        self.received.setVisible(self.method == "cash")
        if self.method == "mixed":
            self.split_model.set_rows([])
            self.payments = []

    def _on_received(self) -> None:
        received = self.received.cents()
        self.received_cents = received
        change = max(0, received - self.total_cents)
        self.change_label.setText(format_money(cents_to_money(change),
                                               self.services.money_symbol()))

    def _add_split(self) -> None:
        amount = self.split_amount.cents()
        if amount <= 0:
            return
        self.payments.append({"method": self.split_method.currentData(),
                              "amount_cents": amount})
        self.split_model.set_rows(self.payments)
        paid = sum(p["amount_cents"] for p in self.payments)
        if paid < self.total_cents:
            remaining = self.total_cents - paid
            self.payments.append({"method": "cash", "amount_cents": remaining})
            rows = list(self.payments)
            self.split_model.set_rows(rows)

    def _validate(self) -> None:
        if self.method == "credit" and not self.customer_id:
            error(self, "Un client est obligatoire pour une vente \u00e0 cr\u00e9dit")
            return
        if self.method == "mixed":
            paid = sum(p["amount_cents"] for p in self.payments)
            if paid < self.total_cents:
                self.payments.append({"method": "cash",
                                      "amount_cents": self.total_cents - paid})
        else:
            self.payments = []
        if self.method == "cash" and self.received.cents() < self.total_cents:
            error(self, tr("pos.insufficient"))
            return
        self.received_cents = self.received.cents() if self.method == "cash" \
            else self.total_cents
        self.accept()


class ReceiptDialog(QDialog):
    """Post-sale dialog: print thermal receipt or A4/A5 invoice."""

    def __init__(self, services, sale: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.sale = sale
        self.setWindowTitle(tr("pos.sale_validated", number=sale["number"]))
        self.resize(460, 260)
        layout = QVBoxLayout(self)
        title = QLabel(tr("pos.sale_validated", number=sale["number"]))
        title.setStyleSheet("font-weight:700;font-size:12pt;color:#15803D")
        layout.addWidget(title)
        total = QLabel(format_money(cents_to_money(sale["total_cents"]),
                                    services.money_symbol()))
        total.setObjectName("PosTotalValue")
        layout.addWidget(total)
        row = QHBoxLayout()
        row.addWidget(button(tr("pos.print_receipt"),
                             lambda: self._print("thermal80"), icon="\U0001F9FE"))
        row.addWidget(button(tr("pos.print_invoice"),
                             lambda: self._print("a4"), icon="\U0001F5A8"))
        layout.addLayout(row)
        layout.addWidget(button(tr("common.close"), self.accept, kind="primary"))

    def _print(self, paper: str) -> None:
        sale = self.services.sales.get_sale(self.sale["id"])
        document = render.render_document(self.services, "receipt", sale, paper)
        printer = self.services.settings.get("print.receipt_printer", "") \
            if paper.startswith("thermal") else \
            self.services.settings.get("print.default_printer", "")
        if paper.startswith("thermal") and printer:
            render.print_document(document, printer, 1, paper)
            info(self, tr("print.printed"))
        else:
            dialog = PrintDialog(self.services, document, paper=paper, parent=self)
            dialog.exec()


class HeldSalesDialog(QDialog):
    def __init__(self, services, held: list[dict], parent=None):
        super().__init__(parent)
        self.services = services
        self.result: dict | None = None
        self.setWindowTitle(tr("pos.held_sales"))
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for row in held:
            label_text = f"{row['label']}  -  {row['created_at']}"
            item = QListWidgetItem(label_text)
            item.setData(Qt.UserRole, row)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.select"), self._pick, kind="primary"))
        actions.addWidget(button(tr("common.delete"), self._delete, kind="danger"))
        layout.addLayout(actions)

    def _pick(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        row = item.data(Qt.UserRole)
        self.result = self.services.sales.release_held(row["id"])
        self.accept()

    def _delete(self) -> None:
        item = self.list.currentItem()
        if item:
            self.services.sales.cancel_held(item.data(Qt.UserRole)["id"])
            self.list.takeItem(self.list.row(item))


class ReturnDialog(QDialog):
    """Pick an original sale, choose quantities to return, restock and issue
    a credit note."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.result: dict | None = None
        self.setWindowTitle(tr("pos.return_mode"))
        self.resize(900, 620)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        search = QLineEdit()
        search.setPlaceholderText(tr("pos.select_original") + " - num\u00e9ro ou client")
        search.returnPressed.connect(lambda: self._search(search.text()))
        layout.addWidget(search)
        self.sales_model = TableModel([
            ("number", tr("common.number"), "text"),
            ("date", tr("common.date"), "datetime"),
            ("customer_name", tr("customers.title"), "text"),
            ("total_cents", tr("common.total"), "money"),
        ])
        self.sales_table = DataTable(self.sales_model)
        self.sales_table.doubleClickedRow.connect(self._select_sale)
        layout.addWidget(self.sales_table, 1)

        self.items_model = TableModel([
            ("product_id", "ID", "int"),
            ("label", tr("common.label"), "text"),
            ("quantity", tr("common.quantity"), "qty"),
            ("returnable", tr("pos.max_returnable"), "text"),
            ("to_return", tr("pos.qty_returned"), "text"),
        ])
        self.items_table = DataTable(self.items_model)
        layout.addWidget(self.items_table, 1)

        form = QHBoxLayout()
        form.addWidget(label(tr("pos.qty_returned") + " :"))
        self.return_qty = QSpinBox()
        self.return_qty.setRange(0, 99999)
        form.addWidget(self.return_qty)
        form.addWidget(button(tr("common.apply"), self._set_qty))
        form.addWidget(label(tr("stock.reason") + " :"))
        self.reason = QLineEdit()
        form.addWidget(self.reason, 1)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.validate"), self._validate, kind="primary"))
        layout.addLayout(actions)
        self._selected_sale = None
        self._search("")

    def _search(self, term: str) -> None:
        rows = self.services.sales.list_sales(limit=100)
        term = (term or "").strip().lower()
        if term:
            rows = [r for r in rows if term in (r["number"] + (r.get("customer_name") or "")).lower()]
        self.sales_model.set_rows(rows)

    def _select_sale(self, row: dict) -> None:
        self._selected_sale = row
        sale = self.services.sales.get_sale(row["id"])
        rows = []
        for item in sale["items"]:
            if item.get("product_id"):
                returnable = self.services.sales.returnable_quantity(
                    row["id"], item["product_id"])
                rows.append({**item, "returnable": f"{returnable:g}",
                             "to_return": "0"})
        self.items_model.set_rows(rows)

    def _set_qty(self) -> None:
        rows = self.items_model.rows
        current = self.items_table.selected_row()
        if not current:
            return
        for row in rows:
            if row["id"] == current["id"]:
                row["to_return"] = str(self.return_qty.value())
        self.items_model.set_rows(rows)

    def _validate(self) -> None:
        if not self._selected_sale:
            return
        returns = []
        for row in self.items_model.rows:
            quantity = to_decimal(row.get("to_return", 0))
            if quantity > 0:
                returns.append({"product_id": row["product_id"], "qty": quantity})
        if not returns:
            error(self, tr("common.no_data"))
            return
        session = self.services.cash.current_session()
        try:
            result = self.services.sales.create_return(
                self._selected_sale["id"], returns,
                reason=self.reason.text().strip() or "Retour client",
                user_id=self.services.user_id,
                cash_session_id=session.get("id") if session else None,
                audit=self.services.log)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.result = result
        self.accept()
