"""Dépenses: 11 catégories, saisie, totaux par période, export."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDateEdit, QFormLayout, QHBoxLayout,
                               QLineEdit, QTextEdit, QVBoxLayout)

from PySide6.QtCore import QDate

from ...i18n import tr
from ..widgets.common import (DataTable, MoneySpin, TableModel, button, error, info,
                              label)
from ..widgets.list_screen import ListScreen

METHODS = (("cash", "pay.cash"), ("card", "pay.card"), ("transfer", "pay.transfer"),
           ("check", "pay.check"))


class ExpensesScreen(ListScreen):
    module = "expenses"
    subtitle = tr("expenses.title")
    export_name = "depenses"

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("category_name", tr("common.category"), "text"),
        ("description", tr("common.description"), "text"),
        ("amount_cents", tr("common.amount"), "money"),
        ("method", tr("pay.method"), "payment"),
        ("supplier_name", tr("suppliers.title"), "text"),
    ]

    def filter_specs(self) -> list[dict]:
        return [{"field": "category_id", "options": lambda: [
            (c["name"], c["id"]) for c in self.services.catalog.categories(kind="expense")]}]

    def load_rows(self) -> list[dict]:
        return self.services.expenses.list(limit=3000)

    def build(self) -> None:
        super().build()
        self.total_label = label("", "MoneyLabel")
        self.root.insertWidget(self.root.count() - 1, self.total_label)

    def refresh(self) -> None:
        super().refresh()
        if self._built:
            total = sum(int(row.get("amount_cents", 0)) for row in self.model.rows)
            from ...core.money import cents_to_money, format_money

            self.total_label.setText(
                f"{tr('expenses.total')} : <b>"
                f"{format_money(cents_to_money(total), self.services.money_symbol())}</b>")

    def create_editor(self, row: dict | None) -> None:
        dialog = ExpenseEditor(self.services, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        self.services.expenses.delete(row["id"])
        self.services.log("expense.delete", entity_type="expense", entity_id=row["id"],
                          details=row.get("number", ""))


class ExpenseEditor(QDialog):
    def __init__(self, services, row: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.row = row or {}
        self.setWindowTitle(tr("expenses.new") if not row else tr("common.edit"))
        self.resize(520, 560)
        form = QFormLayout(self)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        if self.row.get("date"):
            self.date.setDate(QDate.fromString(self.row["date"][:10], "yyyy-MM-dd"))
        else:
            self.date.setDate(QDate.currentDate())
        form.addRow(tr("common.date"), self.date)
        self.category = QComboBox()
        self.category.addItem("", None)
        for category in services.catalog.categories(kind="expense"):
            self.category.addItem(category["name"], category["id"])
        if self.row.get("category_id"):
            index = self.category.findData(self.row["category_id"])
            if index >= 0:
                self.category.setCurrentIndex(index)
        form.addRow(tr("common.category"), self.category)
        self.description = QLineEdit(self.row.get("description", ""))
        form.addRow(tr("common.description"), self.description)
        self.amount = MoneySpin()
        self.amount.setCents(self.row.get("amount_cents", 0))
        form.addRow(tr("common.amount"), self.amount)
        self.method = QComboBox()
        for code, key in METHODS:
            self.method.addItem(tr(key), code)
        if self.row.get("method"):
            index = self.method.findData(self.row["method"])
            if index >= 0:
                self.method.setCurrentIndex(index)
        form.addRow(tr("pay.method"), self.method)
        self.supplier = QComboBox()
        self.supplier.addItem("", None)
        for supplier in services.catalog.parties("suppliers"):
            self.supplier.addItem(supplier["name"], supplier["id"])
        if self.row.get("supplier_id"):
            index = self.supplier.findData(self.row["supplier_id"])
            if index >= 0:
                self.supplier.setCurrentIndex(index)
        form.addRow(tr("suppliers.title"), self.supplier)
        self.notes = QTextEdit()
        self.notes.setPlainText(self.row.get("notes", ""))
        self.notes.setMaximumHeight(80)
        form.addRow(tr("common.notes"), self.notes)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        form.addRow(actions)

    def _save(self) -> None:
        if self.amount.cents() <= 0 or not self.description.text().strip():
            error(self, tr("common.required_fields"))
            return
        session = self.services.cash.current_session()
        result = self.services.expenses.save(
            date=self.date.date().toString("yyyy-MM-dd"),
            category_id=self.category.currentData(),
            description=self.description.text().strip(),
            amount_cents=self.amount.cents(),
            method=self.method.currentData(),
            supplier_id=self.supplier.currentData(),
            notes=self.notes.toPlainText(),
            cash_session_id=session.get("id") if session else None,
            user_id=self.services.user_id,
            expense_id=self.row.get("id"))
        self.services.log("expense.save", entity_type="expense",
                          entity_id=result.get("id"),
                          details=f"{result.get('number')} {result['amount_cents'] / 100}")
        self.accept()
