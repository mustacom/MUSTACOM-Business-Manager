"""Paiements: encaissements clients et décaissements fournisseurs, avec
imputation sur factures."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QVBoxLayout)

from ...core.money import cents_to_money, format_money
from ...i18n import tr
from ..widgets.common import (MoneySpin, TableModel, button, error, info, label)
from ..widgets.list_screen import ListScreen

METHODS = (("cash", "pay.cash"), ("card", "pay.card"), ("transfer", "pay.transfer"),
           ("check", "pay.check"))


class PaymentsScreen(ListScreen):
    module = "payments"
    subtitle = tr("payments.title")
    export_name = "paiements"

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("direction", tr("payments.direction"), "text"),
        ("party_name", tr("common.third_party"), "text"),
        ("amount_cents", tr("common.amount"), "money"),
        ("method", tr("pay.method"), "payment"),
        ("reference", tr("common.reference"), "text"),
    ]

    def filter_specs(self) -> list[dict]:
        return [{"field": "direction", "options": lambda: [
            (tr("payments.in"), "in"), (tr("payments.out"), "out")]}]

    def load_rows(self) -> list[dict]:
        rows = self.services.payments.list(limit=3000)
        for row in rows:
            table = "customers" if row.get("party_type") == "customer" else "suppliers"
            party = self.services.db.fetch(table, row["party_id"]) \
                if row.get("party_id") else {}
            row["party_name"] = (party or {}).get("name", "")
        return rows

    def create_editor(self, row: dict | None) -> None:
        if row:
            info(self, tr("doc.not_editable"))
            return
        dialog = PaymentEditor(self.services, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        self.services.payments.delete(row["id"])
        self.services.log("payment.delete", entity_type="payment", entity_id=row["id"],
                          details=row.get("number", ""))


class PaymentEditor(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(tr("payments.new"))
        self.resize(640, 620)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.direction = QComboBox()
        self.direction.addItem(tr("payments.in"), "in")
        self.direction.addItem(tr("payments.out"), "out")
        self.direction.currentIndexChanged.connect(self._load_parties)
        form.addRow(tr("payments.direction"), self.direction)
        self.party = QComboBox()
        form.addRow(tr("common.third_party"), self.party)
        self.amount = MoneySpin()
        form.addRow(tr("common.amount"), self.amount)
        self.method = QComboBox()
        for code, key in METHODS:
            self.method.addItem(tr(key), code)
        form.addRow(tr("pay.method"), self.method)
        self.reference = QLineEdit()
        form.addRow(tr("common.reference"), self.reference)
        root.addLayout(form)

        root.addWidget(label(tr("payments.allocate_invoices")))
        self.invoice_list = QListWidget()
        root.addWidget(self.invoice_list, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)
        self._load_parties()

    def _load_parties(self) -> None:
        self.party.clear()
        table = "customers" if self.direction.currentData() == "in" else "suppliers"
        for party in self.services.catalog.parties(table):
            self.party.addItem(party["name"], party["id"])
        self.invoice_list.clear()
        if self.direction.currentData() == "in":
            for invoice in self.services.invoices.list_unpaid():
                remaining = int(invoice["total_cents"]) - int(invoice["paid_cents"])
                item = QListWidgetItem(
                    f"{invoice['number']}  -  "
                    f"{format_money(cents_to_money(remaining), self.services.money_symbol())}")
                item.setData(Qt.UserRole, invoice["id"])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.invoice_list.addItem(item)

    def _save(self) -> None:
        party_id = self.party.currentData()
        if not party_id or self.amount.cents() <= 0:
            error(self, tr("common.required_fields"))
            return
        invoice_ids = [self.invoice_list.item(index).data(Qt.UserRole)
                       for index in range(self.invoice_list.count())
                       if self.invoice_list.item(index).checkState() == Qt.Checked]
        session = self.services.cash.current_session()
        result = self.services.payments.save(
            direction=self.direction.currentData(),
            party_type="customer" if self.direction.currentData() == "in" else "supplier",
            party_id=party_id, amount_cents=self.amount.cents(),
            method=self.method.currentData(),
            reference=self.reference.text().strip(),
            invoice_ids=invoice_ids if self.direction.currentData() == "in" else [],
            cash_session_id=session.get("id") if session else None,
            user_id=self.services.user_id)
        self.services.log("payment.save", entity_type="payment",
                          entity_id=result.get("id"),
                          details=f"{result.get('number')} {result['amount_cents'] / 100}")
        self.accept()
