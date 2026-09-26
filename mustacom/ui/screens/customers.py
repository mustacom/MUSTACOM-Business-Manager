"""Customers and suppliers: database, editor form with Moroccan fiscal IDs,
balance, printable account statement."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLineEdit,
                               QTextEdit, QVBoxLayout)

from ...core.crud import ValidationError
from datetime import date

from ...core.money import cents_to_money, format_money
from ...i18n import tr
from ..dialogs.print_dialog import PrintDialog
from ...reporting import render
from ..widgets.common import (DataTable, FormGrid, MoneySpin, TableModel, button,
                              card, error, info, label, scroll, vbox)
from ..widgets.list_screen import ListScreen


class PartyScreen(ListScreen):
    table_name = "customers"
    code_prefix = "CLI"
    statement_kind = "statement_customer"

    columns = [
        ("code", tr("customers.code"), "text"),
        ("name", tr("common.name"), "text"),
        ("company", tr("customers.company"), "text"),
        ("city", tr("customers.city"), "text"),
        ("phone", tr("customers.phone"), "text"),
        ("email", tr("customers.email"), "text"),
        ("ice", "ICE", "text"),
        ("balance_cents", tr("customers.balance"), "money"),
        ("credit_limit_cents", tr("customers.credit_limit"), "money"),
        ("is_active", tr("common.active"), "bool"),
    ]

    def build(self) -> None:
        super().build()
        extra = self.toolbar(
            button(tr("customers.statement"), self._statement, icon="\U0001F5CE"),
            stretch=True)
        self.root.insertWidget(1, extra)

    def load_rows(self) -> list[dict]:
        return self.services.catalog.parties(self.table_name)

    def create_editor(self, row: dict | None) -> None:
        dialog = PartyEditor(self.services, self.table_name, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_row(self, row: dict) -> None:
        removed = self.services.catalog.delete_party(self.table_name, row["id"])
        self.services.log(f"{self.table_name[:-1]}.delete", entity_type=self.table_name[:-1],
                          entity_id=row["id"], details=row.get("name", ""))
        if not removed:
            info(self, f"{row.get('name')} : documents existants - compte d\u00e9sactiv\u00e9.",
                 tr("common.info"))

    def _statement(self) -> None:
        row = self.table.selected_row()
        if not row:
            return
        dialog = StatementDialog(self.services, self.table_name, row, parent=self)
        dialog.exec()


class CustomersScreen(PartyScreen):
    module = "customers"
    subtitle = tr("customers.title")
    export_name = "clients"


class SuppliersScreen(PartyScreen):
    module = "suppliers"
    subtitle = tr("suppliers.title")
    table_name = "suppliers"
    code_prefix = "FRS"
    statement_kind = "statement_supplier"
    export_name = "fournisseurs"
    columns = [
        ("code", tr("suppliers.code"), "text"),
        ("name", tr("common.name"), "text"),
        ("contact_person", tr("customers.contact"), "text"),
        ("city", tr("customers.city"), "text"),
        ("phone", tr("customers.phone"), "text"),
        ("email", tr("customers.email"), "text"),
        ("payment_terms", tr("suppliers.payment_terms"), "text"),
        ("balance_cents", tr("customers.balance"), "money"),
        ("is_active", tr("common.active"), "bool"),
    ]


class PartyEditor(QDialog):
    def __init__(self, services, table: str, row: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.table = table
        self.row = row or {}
        self.setWindowTitle((tr("customers.new") if table == "customers"
                             else tr("suppliers.new")) if not row else
                            (tr("common.edit")))
        self.resize(760, 720)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = FormGrid(columns=2)
        self.code = QLineEdit(self.row.get("code", ""))
        form.add(tr("common.code"), self.code)
        self.name = QLineEdit(self.row.get("name", ""))
        form.add(tr("common.name"), self.name, required=True)
        self.company = QLineEdit(self.row.get("company", ""))
        form.add(tr("customers.company"), self.company)
        if self.table == "customers":
            self.kind = QComboBox()
            for code, key in (("individual", "customers.type_individual"),
                              ("company", "customers.type_company"),
                              ("association", "customers.type_association"),
                              ("school", "customers.type_school"),
                              ("public", "customers.type_public")):
                self.kind.addItem(tr(key), code)
            current = self.row.get("customer_type", "individual")
            self.kind.setCurrentIndex(self.kind.findData(current))
            form.add(tr("customers.type"), self.kind)
        else:
            self.contact = QLineEdit(self.row.get("contact_person", ""))
            form.add(tr("customers.contact"), self.contact)
        self.address = QLineEdit(self.row.get("address", ""))
        form.add(tr("customers.address"), self.address, span=2)
        self.city = QLineEdit(self.row.get("city", ""))
        form.add(tr("customers.city"), self.city)
        self.zip = QLineEdit(self.row.get("zip", ""))
        form.add(tr("customers.zip"), self.zip)
        self.country = QLineEdit(self.row.get("country", "Maroc"))
        form.add(tr("customers.country"), self.country)
        self.phone = QLineEdit(self.row.get("phone", ""))
        form.add(tr("customers.phone"), self.phone)
        self.mobile = QLineEdit(self.row.get("mobile", ""))
        form.add("Mobile", self.mobile)
        self.email = QLineEdit(self.row.get("email", ""))
        form.add(tr("customers.email"), self.email)
        self.ice = QLineEdit(self.row.get("ice", ""))
        form.add("ICE", self.ice)
        self.if_number = QLineEdit(self.row.get("if_number", ""))
        form.add("IF", self.if_number)
        self.rc = QLineEdit(self.row.get("rc", ""))
        form.add("RC", self.rc)
        self.payment_terms = QLineEdit(self.row.get("payment_terms", ""))
        form.add(tr("suppliers.payment_terms"), self.payment_terms)
        if self.table == "customers":
            self.credit_limit = MoneySpin()
            self.credit_limit.setCents(self.row.get("credit_limit_cents", 0))
            form.add(tr("customers.credit_limit"), self.credit_limit)
        self.active = QCheckBox(tr("common.active"))
        self.active.setChecked(bool(self.row.get("is_active", 1)))
        form.add("", self.active)
        self.notes = QTextEdit()
        self.notes.setPlainText(self.row.get("notes", ""))
        form.add_full(tr("common.notes"), self.notes)
        root.addWidget(scroll(form_widget(form)), 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)

    def _save(self) -> None:
        data = {
            "code": self.code.text().strip(),
            "name": self.name.text().strip(),
            "company": self.company.text().strip(),
            "address": self.address.text().strip(),
            "city": self.city.text().strip(),
            "zip": self.zip.text().strip(),
            "country": self.country.text().strip(),
            "phone": self.phone.text().strip(),
            "mobile": self.mobile.text().strip(),
            "email": self.email.text().strip(),
            "ice": self.ice.text().strip(),
            "if_number": self.if_number.text().strip(),
            "rc": self.rc.text().strip(),
            "payment_terms": self.payment_terms.text().strip(),
            "notes": self.notes.toPlainText(),
            "is_active": self.active.isChecked(),
        }
        if self.table == "customers":
            data["customer_type"] = self.kind.currentData()
            data["credit_limit_cents"] = self.credit_limit.cents()
        else:
            data["contact_person"] = self.contact.text().strip()
        try:
            self.services.catalog.save_party(self.table, data,
                                             party_id=self.row.get("id"),
                                             user_id=self.services.user_id,
                                             audit=self.services.log)
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.accept()


def form_widget(form: FormGrid):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(form)
    return widget


class StatementDialog(QDialog):
    """Account statement with printable A4 output."""

    def __init__(self, services, table: str, party: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.table = table
        self.party = party
        self.setWindowTitle(f"{tr('customers.statement')} - {party['name']}")
        self.resize(1000, 640)
        layout = QVBoxLayout(self)

        head = QHBoxLayout()
        balance = services.parties.customer_balance(party["id"]) \
            if table == "customers" else services.parties.supplier_balance(party["id"])
        head.addWidget(label(f"<b>{party['name']}</b>  -  "
                             f"{tr('customers.balance')} : "
                             f"<span style='color:{'#C0392B' if balance > 0 else '#15803D'}'>"
                             f"{format_money(cents_to_money(balance), services.money_symbol())}"
                             f"</span>", "MoneyLabel"))
        head.addStretch(1)
        head.addWidget(button(tr("common.print"), self._print, kind="primary",
                              icon="\U0001F5A8"))
        layout.addLayout(head)

        self.model = TableModel([
            ("date", tr("common.date"), "date"),
            ("label", tr("common.label"), "text"),
            ("number", tr("common.reference"), "text"),
            ("debit_cents", "D\u00e9bit", "money"),
            ("credit_cents", "Cr\u00e9dit", "money"),
            ("running_cents", "Solde", "money"),
        ])
        self.table_view = DataTable(self.model, status_columns=())
        layout.addWidget(self.table_view, 1)
        self.refresh()

    def refresh(self) -> None:
        entries = self.services.parties.customer_statement(self.party["id"]) \
            if self.table == "customers" else \
            self.services.parties.supplier_statement(self.party["id"])
        self.entries = entries
        self.model.symbol = self.services.money_symbol()
        self.model.set_rows(entries)

    def _print(self) -> None:
        party = self.services.db.fetch(self.table, self.party["id"])
        document = render.render_document(
            self.services,
            "statement_customer" if self.table == "customers" else "statement_supplier",
            {"number": "", "date": date.today().isoformat(),
             "party": party, "entries": self.entries}, paper="a4")
        dialog = PrintDialog(self.services, document, paper="a4", parent=self)
        dialog.exec()
