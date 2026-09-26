"""Achats: commande fournisseur -> réception (stock) -> facture -> paiement,
plus les retours fournisseur."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QTabWidget, QVBoxLayout, QWidget)

from ...core.money import cents_to_money, format_money, db_to_qty
from ...i18n import tr
from ..widgets.common import (DataTable, MoneySpin, QtySpin, TableModel, button, error,
                              info, label)
from .doc_base import DocListScreen


class PurchasesScreen(DocListScreen):
    module = "purchases"
    subtitle = tr("purchases.title")
    service_attr = "purchases"
    render_kind = "purchase"
    export_name = "achats"

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("supplier_name", tr("suppliers.title"), "text"),
        ("supplier_ref", tr("purchases.ref"), "text"),
        ("total_cents", tr("common.total"), "money"),
        ("status", tr("common.status"), "text"),
    ]

    def status_columns(self) -> tuple[int, ...]:
        return (5,)

    def load_rows(self) -> list[dict]:
        rows = self.service().list(term=self.search.text().strip(), limit=2000)
        for row in rows:
            supplier = self.services.db.fetch("suppliers", row["supplier_id"]) \
                if row.get("supplier_id") else {}
            row["supplier_name"] = (supplier or {}).get("name", "")
        return rows

    def build(self) -> None:
        super().build()
        self.root.insertWidget(2, self.toolbar(
            button(tr("purchases.receive"), self._receive, kind="success", icon="\U0001F4E5"),
            button(tr("purchases.supplier_invoice"), self._invoice, icon="\U0001F9FE"),
            button(tr("purchases.pay"), self._pay, kind="primary", icon="\U0001F4B5"),
            button(tr("purchases.invoices_list"), self._invoices_list, icon="\U0001F4C4"),
            button(tr("suppliers.returns"), self._supplier_return, icon="\u21A9"),
            stretch=True))

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
        ]

    # ------------------------------------------------------------------
    def _purchase(self) -> dict | None:
        row = self.table.selected_row()
        return self.service().get(row["id"]) if row else None

    def _receive(self) -> None:
        purchase = self._purchase()
        if not purchase or not self.require("validate"):
            return
        dialog = ReceiveDialog(self.services, purchase, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def _invoice(self) -> None:
        purchase = self._purchase()
        if not purchase or not self.require("create"):
            return
        invoice = self.service().create_supplier_invoice(
            purchase["id"], user_id=self.services.user_id)
        self.services.log("purchase.invoice", entity_type="purchase",
                          entity_id=purchase["id"], details=invoice["number"])
        info(self, tr("purchases.invoice_created", number=invoice["number"]),
             tr("common.success"))
        self.refresh()

    def _pay(self) -> None:
        purchase = self._purchase()
        if not purchase or not self.require("validate"):
            return
        invoices = self.services.purchases.supplier_invoices()
        pending = [i for i in invoices if i["purchase_id"] == purchase["id"]
                   and int(i["paid_cents"]) < int(i["total_cents"])]
        if not pending:
            info(self, tr("purchases.no_pending_invoice"))
            return
        invoice = pending[0]
        remaining = int(invoice["total_cents"]) - int(invoice["paid_cents"])
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("purchases.pay"))
        dialog.resize(420, 280)
        form = QFormLayout(dialog)
        form.addRow(tr("common.number"), label(invoice["number"]))
        form.addRow(tr("invoices.remaining"), label(
            format_money(cents_to_money(remaining), self.services.money_symbol()),
            "MoneyLabel"))
        amount = MoneySpin()
        amount.setCents(remaining)
        form.addRow(tr("common.amount"), amount)
        method = QComboBox()
        for code, key in (("transfer", "pay.transfer"), ("check", "pay.check"),
                          ("cash", "pay.cash"), ("card", "pay.card")):
            method.addItem(tr(key), code)
        form.addRow(tr("pay.method"), method)
        reference = QLineEdit()
        form.addRow(tr("common.reference"), reference)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.validate"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        session = self.services.cash.current_session()
        self.service().pay_supplier_invoice(
            invoice["id"], amount.cents(), method.currentData(),
            reference=reference.text().strip(), user_id=self.services.user_id,
            cash_session_id=session.get("id") if session else None)
        self.services.log("purchase.pay", entity_type="purchase_invoice",
                          entity_id=invoice["id"],
                          details=f"{invoice['number']} +{amount.cents() / 100}")
        self.refresh()
        self.notify_change()

    def _invoices_list(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("purchases.invoices_list"))
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        model = TableModel([
            ("number", tr("common.number"), "text"),
            ("date", tr("common.date"), "date"),
            ("supplier_name", tr("suppliers.title"), "text"),
            ("total_cents", tr("common.total"), "money"),
            ("paid_cents", tr("common.paid"), "money"),
            ("status", tr("common.status"), "text"),
        ])
        model.symbol = self.services.money_symbol()
        table = DataTable(model, status_columns=(5,))
        rows = self.services.purchases.supplier_invoices()
        for row in rows:
            supplier = self.services.db.fetch("suppliers", row["supplier_id"]) \
                if row.get("supplier_id") else {}
            row["supplier_name"] = (supplier or {}).get("name", "")
        model.set_rows(rows)
        layout.addWidget(table)
        layout.addWidget(button(tr("common.close"), dialog.reject))
        dialog.exec()

    def _supplier_return(self) -> None:
        purchase = self._purchase()
        if not purchase or not self.require("create"):
            return
        dialog = SupplierReturnDialog(self.services, purchase, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()


class ReceiveDialog(QDialog):
    def __init__(self, services, purchase: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.purchase = purchase
        self.setWindowTitle(tr("purchases.receive") + " - " + purchase["number"])
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        self.model = TableModel([
            ("code", tr("products.sku"), "text"),
            ("label", tr("common.label"), "text"),
            ("quantity", tr("common.quantity"), "qty"),
            ("received_qty", tr("purchases.received"), "qty"),
        ])
        self.table = DataTable(self.model, status_columns=())
        self.model.set_rows(purchase["items"])
        layout.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.qty = QtySpin()
        bar.addWidget(label(tr("purchases.receive_qty")))
        bar.addWidget(self.qty)
        bar.addWidget(button(tr("common.apply"), self._apply))
        bar.addWidget(button(tr("purchases.receive_all"), self._all))
        bar.addStretch(1)
        layout.addLayout(bar)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.validate"), self._save, kind="primary"))
        layout.addLayout(actions)
        self.received: dict[int, float] = {}

    def _apply(self) -> None:
        row = self.table.selected_row()
        if row:
            self.received[row["id"]] = float(self.qty.qty())

    def _all(self) -> None:
        for item in self.purchase["items"]:
            missing = db_to_qty(int(item["quantity"]) - int(item["received_qty"]))
            if missing > 0:
                self.received[item["id"]] = float(missing)

    def _save(self) -> None:
        from decimal import Decimal

        if not self.received:
            error(self, tr("common.no_data"))
            return
        self.services.purchases.receive(
            self.purchase["id"],
            {item_id: Decimal(str(quantity)) for item_id, quantity in self.received.items()},
            user_id=self.services.user_id)
        self.services.log("purchase.receive", entity_type="purchase",
                          entity_id=self.purchase["id"], details=self.purchase["number"])
        self.accept()


class SupplierReturnDialog(QDialog):
    def __init__(self, services, purchase: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.purchase = purchase
        self.setWindowTitle(tr("suppliers.returns") + " - " + purchase["number"])
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        self.model = TableModel([
            ("code", tr("products.sku"), "text"),
            ("label", tr("common.label"), "text"),
            ("received_qty", tr("purchases.received"), "qty"),
            ("to_return", tr("pos.qty_returned"), "amount"),
        ])
        self.table = DataTable(self.model, status_columns=())
        self.rows = [{**item, "to_return": 0} for item in purchase["items"]]
        self.model.set_rows(self.rows)
        layout.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.qty = QtySpin()
        bar.addWidget(label(tr("pos.qty_returned")))
        bar.addWidget(self.qty)
        bar.addWidget(button(tr("common.apply"), self._apply))
        self.reason = QLineEdit()
        self.reason.setPlaceholderText(tr("stock.reason"))
        bar.addWidget(self.reason, 1)
        layout.addLayout(bar)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.validate"), self._save, kind="primary"))
        layout.addLayout(actions)

    def _apply(self) -> None:
        row = self.table.selected_row()
        if row is not None:
            for item in self.rows:
                if item is row:
                    item["to_return"] = self.qty.qty()
            self.model.set_rows(self.rows)

    def _save(self) -> None:
        from decimal import Decimal

        items = [{"product_id": row["product_id"], "code": row["code"],
                  "label": row["label"], "quantity": row["to_return"],
                  "unit_price_cents": row["unit_price_cents"],
                  "vat_rate_bp": row.get("vat_rate_bp", 0)}
                 for row in self.rows if row.get("to_return")]
        if not items:
            error(self, tr("common.no_data"))
            return
        try:
            result = self.services.supplier_returns.save(
                items, supplier_id=self.purchase["supplier_id"], source_type="purchase",
                source_id=self.purchase["id"], source_number=self.purchase["number"],
                reason=self.reason.text().strip(), user_id=self.services.user_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.services.log("supplier_return.save", entity_type="return_supplier",
                          entity_id=result.get("id"), details=result.get("number", ""))
        self.accept()
