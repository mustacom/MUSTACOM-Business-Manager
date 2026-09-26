"""Réparation informatique: tickets, 7 statuts, dépôt/acompte, facturation."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout,
                               QLineEdit, QListWidget, QListWidgetItem, QTextEdit,
                               QVBoxLayout)

from ...core.money import db_to_qty
from ...i18n import tr
from ...reporting import render
from ..dialogs.print_dialog import PrintDialog
from ..widgets.common import (MoneySpin, button, error, info, label)
from ..widgets.list_screen import ListScreen

REPAIR_STATUSES = ("received", "diagnosing", "waiting_parts", "repairing",
                   "testing", "ready", "delivered")


class RepairsScreen(ListScreen):
    module = "repairs"
    subtitle = tr("repairs.title")
    export_name = "reparations"

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("customer_name", tr("customers.title"), "text"),
        ("device_type", tr("repairs.device_type"), "text"),
        ("device_brand", tr("common.brand"), "text"),
        ("problem", tr("repairs.problem"), "text"),
        ("total_cents", tr("common.total"), "money"),
        ("status", tr("common.status"), "status"),
    ]

    def status_columns(self) -> tuple[int, ...]:
        return (7,)

    def filter_specs(self) -> list[dict]:
        return [{"field": "status", "options": lambda: [
            (tr(f"status.{code}"), code) for code in REPAIR_STATUSES]}]

    def build(self) -> None:
        super().build()
        self.root.insertWidget(1, self.toolbar(
            button(tr("repairs.change_status"), self._change_status, icon="\u21BB"),
            button(tr("repairs.print_ticket"), self._print_ticket, icon="\U0001F9FE"),
            button(tr("repairs.invoice"), self._invoice, kind="success", icon="\U0001F4B5"),
            stretch=True))

    def load_rows(self) -> list[dict]:
        status = ""
        for combo in self.filters:
            if combo.currentData():
                status = combo.currentData()
        return self.services.repairs.list(status=status, limit=2000)

    def refresh(self) -> None:
        if not self._built:
            return
        self.model.symbol = self.services.money_symbol()
        rows = self.load_rows()
        term = self.search.text().strip().lower()
        if term:
            rows = [r for r in rows if term in " ".join(
                str(r.get(k, "")).lower() for k in self.search_fields())]
        self.model.set_rows(rows)
        self.count_label.setText(tr("common.rows", count=len(rows)))

    def create_editor(self, row: dict | None) -> None:
        doc = self.services.repairs.get(row["id"]) if row else None
        dialog = RepairEditor(self.services, doc, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        self.services.db.delete("repairs", row["id"])
        self.services.log("repair.delete", entity_type="repair", entity_id=row["id"],
                          details=row.get("number", ""))

    # ------------------------------------------------------------------
    def _repair(self) -> dict | None:
        row = self.table.selected_row()
        return self.services.repairs.get(row["id"]) if row else None

    def _change_status(self) -> None:
        repair = self._repair()
        if not repair or not self.require("validate"):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("repairs.change_status"))
        dialog.resize(360, 180)
        form = QFormLayout(dialog)
        combo = QComboBox()
        for code in REPAIR_STATUSES:
            combo.addItem(tr(f"status.{code}"), code)
        index = combo.findData(repair.get("status"))
        if index >= 0:
            combo.setCurrentIndex(index)
        form.addRow(tr("common.status"), combo)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.validate"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        self.services.repairs.set_status(repair["id"], combo.currentData(),
                                         user_id=self.services.user_id)
        self.services.log("repair.status", entity_type="repair", entity_id=repair["id"],
                          details=f"{repair['number']} -> {combo.currentData()}")
        self.refresh()
        self.notify_change()

    def _print_ticket(self) -> None:
        repair = self._repair()
        if not repair:
            return
        document = render.render_document(self.services, "repair", repair, "a5")
        dialog = PrintDialog(self.services, document, paper="a5", parent=self)
        dialog.exec()

    def _invoice(self) -> None:
        repair = self._repair()
        if not repair or not self.require("validate"):
            return
        try:
            invoice = self.services.repairs.invoice_repair(repair["id"],
                                                           user_id=self.services.user_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.services.log("repair.invoice", entity_type="repair",
                          entity_id=repair["id"], details=invoice.get("number", ""))
        info(self, tr("repairs.invoiced", number=invoice.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()


class RepairEditor(QDialog):
    def __init__(self, services, doc: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.doc = doc or {}
        self.setWindowTitle(tr("repairs.new") if not doc else
                            f"{tr('repairs.title')} - {doc.get('number', '')}")
        self.resize(760, 720)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.customer = QComboBox()
        for party in services.catalog.parties("customers"):
            self.customer.addItem(party["name"], party["id"])
        if self.doc.get("customer_id"):
            index = self.customer.findData(self.doc["customer_id"])
            if index >= 0:
                self.customer.setCurrentIndex(index)
        form.addRow(tr("customers.title"), self.customer)
        self.device_type = QLineEdit(self.doc.get("device_type", ""))
        form.addRow(tr("repairs.device_type"), self.device_type)
        self.device_brand = QLineEdit(self.doc.get("device_brand", ""))
        form.addRow(tr("common.brand"), self.device_brand)
        self.device_model = QLineEdit(self.doc.get("device_model", ""))
        form.addRow(tr("repairs.device_model"), self.device_model)
        self.serial = QLineEdit(self.doc.get("serial_number", ""))
        form.addRow(tr("repairs.serial"), self.serial)
        self.accessories = QLineEdit(self.doc.get("accessories", ""))
        form.addRow(tr("repairs.accessories"), self.accessories)
        self.problem = QTextEdit()
        self.problem.setPlainText(self.doc.get("problem", ""))
        self.problem.setMaximumHeight(70)
        form.addRow(tr("repairs.problem"), self.problem)
        self.diagnosis = QTextEdit()
        self.diagnosis.setPlainText(self.doc.get("diagnosis", ""))
        self.diagnosis.setMaximumHeight(70)
        form.addRow(tr("repairs.diagnosis"), self.diagnosis)
        self.repair_performed = QTextEdit()
        self.repair_performed.setPlainText(self.doc.get("repair_performed", ""))
        self.repair_performed.setMaximumHeight(70)
        form.addRow(tr("repairs.performed"), self.repair_performed)
        self.labor = MoneySpin()
        self.labor.setCents(self.doc.get("labor_cents", 0))
        form.addRow(tr("repairs.labor"), self.labor)
        self.deposit = MoneySpin()
        self.deposit.setCents(self.doc.get("deposit_cents", 0))
        form.addRow(tr("repairs.deposit"), self.deposit)
        self.eta = QDateEdit()
        self.eta.setCalendarPopup(True)
        self.eta.setDisplayFormat("dd/MM/yyyy")
        self.eta.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        self.eta.setDate(QDate.currentDate().addDays(2))
        form.addRow(tr("repairs.eta"), self.eta)
        root.addLayout(form)

        root.addWidget(label(tr("repairs.parts_used")))
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("pos.search_product"))
        self.search.textChanged.connect(self._results)
        search_row.addWidget(self.search, 2)
        self.parts_list = QListWidget()
        self.parts_list.setMaximumHeight(90)
        self.results = QListWidget()
        self.results.setMaximumHeight(90)
        self.results.itemDoubleClicked.connect(self._add_part)
        root.addLayout(search_row)
        root.addWidget(self.results)
        root.addWidget(self.parts_list)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)
        self.parts: list[dict] = [
            {**part, "quantity": db_to_qty(int(part["quantity"]))}
            for part in self.doc.get("items", [])]
        self._render_parts()

    def _render_parts(self) -> None:
        self.parts_list.clear()
        for part in self.parts:
            self.parts_list.addItem(
                f"{part.get('label', '')} x {part.get('quantity', 0):g}")

    def _results(self, term: str) -> None:
        self.results.clear()
        if not term.strip():
            return
        for row in self.services.sales.search(term, limit=10, include_services=False):
            item = QListWidgetItem(f"{row['name']} - {row['code']}")
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)

    def _add_part(self, list_item: QListWidgetItem) -> None:
        row = list_item.data(Qt.UserRole)
        self.parts.append({"product_id": row["id"], "code": row["code"],
                           "label": row["name"], "quantity": 1,
                           "unit_price_cents": row["price_cents"],
                           "vat_rate_bp": row.get("vat_rate_bp", 2000)})
        self._render_parts()

    def _save(self) -> None:
        if not self.device_type.text().strip():
            error(self, tr("common.required_fields"))
            return
        result = self.services.repairs.save(
            customer_id=self.customer.currentData(),
            device_type=self.device_type.text().strip(),
            device_brand=self.device_brand.text().strip(),
            device_model=self.device_model.text().strip(),
            serial_number=self.serial.text().strip(),
            accessories=self.accessories.text().strip(),
            problem=self.problem.toPlainText(),
            diagnosis=self.diagnosis.toPlainText(),
            repair_performed=self.repair_performed.toPlainText(),
            labor_cents=self.labor.cents(),
            parts=self.parts,
            deposit_cents=self.deposit.cents(),
            eta=self.eta.date().toString("yyyy-MM-dd"),
            user_id=self.services.user_id,
            repair_id=self.doc.get("id"))
        self.services.log("repair.save", entity_type="repair",
                          entity_id=result.get("id"), details=result.get("number", ""))
        self.accept()
