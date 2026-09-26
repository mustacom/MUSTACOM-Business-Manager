"""Factures clients: encaissement, annulation, avoir, impression A4/A5."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLineEdit, QVBoxLayout

from ...core.money import cents_to_money, format_money
from ...i18n import tr
from ..widgets.common import (MoneySpin, button, confirm, error, info, label)
from .doc_base import DocListScreen

PAY_METHODS = (("cash", "pay.cash"), ("card", "pay.card"), ("transfer", "pay.transfer"),
               ("check", "pay.check"))


class InvoicesScreen(DocListScreen):
    module = "invoices"
    subtitle = tr("invoices.title")
    service_attr = "invoices"
    render_kind = "invoice"
    export_name = "factures"
    editable_statuses = ()          # factures are not edited after creation

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("party_name", tr("customers.title"), "text"),
        ("invoice_type", tr("common.type"), "text"),
        ("total_cents", tr("common.total"), "money"),
        ("paid_cents", tr("common.paid"), "money"),
        ("status", tr("common.status"), "text"),
    ]

    def status_columns(self) -> tuple[int, ...]:
        return (6,)

    def load_rows(self) -> list[dict]:
        rows = self.service().list(term=self.search.text().strip(), limit=2000)
        return [r for r in rows if r.get("invoice_type", "standard") != "credit_note"]

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
            (tr("invoices.record_payment"), self._record_payment, {"kind": "success",
                                                                  "icon": "\U0001F4B5"}),
            (tr("invoices.credit_note"), self._credit_note, {"icon": "\u21A9"}),
            (tr("invoices.cancel"), self._cancel, {"kind": "danger"}),
        ]

    def _selected_invoice(self) -> dict | None:
        row = self.table.selected_row()
        return self.service().get(row["id"]) if row else None

    def _record_payment(self) -> None:
        invoice = self._selected_invoice()
        if not invoice:
            return
        if not self.require("validate"):
            return
        remaining = int(invoice["total_cents"]) - int(invoice["paid_cents"])
        if remaining <= 0:
            info(self, tr("invoices.already_paid"))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("invoices.record_payment"))
        dialog.resize(420, 300)
        form = QFormLayout(dialog)
        form.addRow(tr("common.number"), label(invoice["number"]))
        form.addRow(tr("invoices.remaining"), label(
            format_money(cents_to_money(remaining), self.services.money_symbol()),
            "MoneyLabel"))
        amount = MoneySpin()
        amount.setCents(remaining)
        form.addRow(tr("common.amount"), amount)
        from PySide6.QtWidgets import QComboBox

        method = QComboBox()
        for code, key in PAY_METHODS:
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
        self.service().record_payment(
            invoice["id"], amount.cents(), method.currentData(),
            reference=reference.text().strip(), user_id=self.services.user_id,
            cash_session_id=session.get("id") if session else None)
        self.services.log("invoice.payment", entity_type="invoice",
                          entity_id=invoice["id"],
                          details=f"{invoice['number']} +{amount.cents() / 100}")
        self.refresh()
        self.notify_change()

    def _credit_note(self) -> None:
        invoice = self._selected_invoice()
        if not invoice:
            return
        if not self.require("create"):
            return
        if not confirm(self, tr("invoices.credit_note"),
                       tr("invoices.credit_note_confirm", number=invoice["number"]),
                       destructive=True):
            return
        from ...core.documents import items_to_cart
        from ...core.sales import CartItem

        credit = self.service().create_credit_note(
            customer_id=invoice["customer_id"],
            items=items_to_cart(invoice["items"], CartItem),
            invoice_id=invoice["id"], reason="Avoir total",
            user_id=self.services.user_id)
        self.services.log("invoice.credit_note", entity_type="credit_note",
                          entity_id=credit.get("id"), details=credit.get("number", ""))
        info(self, tr("invoices.credit_note_created", number=credit.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()

    def _cancel(self) -> None:
        invoice = self._selected_invoice()
        if not invoice:
            return
        if not self.require("delete"):
            return
        if not confirm(self, tr("invoices.cancel"),
                       tr("invoices.cancel_confirm", number=invoice["number"]),
                       destructive=True):
            return
        try:
            self.service().cancel(invoice["id"], user_id=self.services.user_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.services.log("invoice.cancel", entity_type="invoice",
                          entity_id=invoice["id"], details=invoice["number"])
        self.refresh()
        self.notify_change()


class CreditNotesScreen(DocListScreen):
    module = "credit_notes"
    subtitle = tr("credit_notes.title")
    service_attr = "credit_notes"
    render_kind = "credit_note"
    export_name = "avoirs"
    editable_statuses = ()

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("customer_name", tr("customers.title"), "text"),
        ("total_cents", tr("common.total"), "money"),
        ("reason", tr("stock.reason"), "text"),
        ("status", tr("common.status"), "text"),
    ]

    def status_columns(self) -> tuple[int, ...]:
        return (5,)

    def load_rows(self) -> list[dict]:
        return self.service().list(term=self.search.text().strip(), limit=2000)

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
        ]

    def create_editor(self, row: dict | None) -> None:
        error(self, tr("doc.not_editable"))

    def delete_row(self, row: dict) -> None:
        error(self, tr("doc.not_editable"))
        raise RuntimeError("blocked")
