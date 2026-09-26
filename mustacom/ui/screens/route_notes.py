"""Bons de route: driver/vehicle, destination, km, linked delivery items."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout)

from ...core.money import db_to_qty
from ...i18n import tr
from ..widgets.common import (DataTable, TableModel, button, error, info, label)
from .doc_base import DocListScreen


class RouteNotesScreen(DocListScreen):
    module = "route_notes"
    subtitle = tr("route.title")
    service_attr = "route_notes"
    render_kind = "route"
    export_name = "bons-route"

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("party_name", tr("customers.title"), "text"),
        ("destination", tr("route.destination"), "text"),
        ("km", tr("route.km"), "int"),
        ("status", tr("common.status"), "text"),
    ]

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
            (tr("common.validate"), lambda: self.validate_selected("validated"),
             {"kind": "success"}),
        ]

    def load_rows(self) -> list[dict]:
        rows = self.service().list(limit=2000)
        for row in rows:
            row["party_name"] = row.get("customer_name") or ""
        return rows

    def create_editor(self, row: dict | None) -> None:
        doc = self.service().get(row["id"]) if row else None
        dialog = RouteEditor(self.services, doc, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()


class RouteEditor(QDialog):
    def __init__(self, services, doc: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.doc = doc or {}
        self.setWindowTitle(tr("route.title") + " - " +
                            (self.doc.get("number", "") or tr("common.new")))
        self.resize(860, 620)
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
        self.driver = QComboBox()
        self.driver.addItem("", None)
        for driver in services.db.fetch_all("drivers", order="name"):
            self.driver.addItem(driver["name"], driver["id"])
        if self.doc.get("driver_id"):
            index = self.driver.findData(self.doc["driver_id"])
            if index >= 0:
                self.driver.setCurrentIndex(index)
        form.addRow(tr("route.driver"), self.driver)
        self.vehicle = QComboBox()
        self.vehicle.addItem("", None)
        for vehicle in services.db.fetch_all("vehicles", order="registration"):
            self.vehicle.addItem(f"{vehicle['registration']} - {vehicle.get('model', '')}",
                                 vehicle["id"])
        if self.doc.get("vehicle_id"):
            index = self.vehicle.findData(self.doc["vehicle_id"])
            if index >= 0:
                self.vehicle.setCurrentIndex(index)
        form.addRow(tr("route.vehicle"), self.vehicle)
        self.departure = QLineEdit(self.doc.get("departure", ""))
        form.addRow(tr("route.departure"), self.departure)
        self.destination = QLineEdit(self.doc.get("destination", ""))
        form.addRow(tr("route.destination"), self.destination)
        self.km = QSpinBox()
        self.km.setRange(0, 99999)
        self.km.setValue(int(self.doc.get("km", 0)))
        form.addRow(tr("route.km"), self.km)
        root.addLayout(form)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("pos.search_product"))
        self.search.textChanged.connect(self._results)
        search_row.addWidget(self.search, 2)
        self.results = QListWidget()
        self.results.setMaximumHeight(110)
        self.results.itemDoubleClicked.connect(self._add)
        root.addLayout(search_row)
        root.addWidget(self.results)

        self.model = TableModel([
            ("label", tr("common.label"), "text"),
            ("quantity", tr("common.quantity"), "qty"),
        ])
        self.table = DataTable(self.model, status_columns=())
        root.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 99999)
        bar.addWidget(label(tr("common.quantity")))
        bar.addWidget(self.quantity)
        bar.addWidget(button(tr("common.delete"), self._remove, kind="danger"))
        bar.addStretch(1)
        root.addLayout(bar)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)
        self.rows: list[dict] = list(self.doc.get("items", []))
        self.model.set_rows(self.rows)

    def _results(self, term: str) -> None:
        self.results.clear()
        if not term.strip():
            return
        for row in self.services.sales.search(term, limit=15, include_services=False):
            item = QListWidgetItem(f"{row['name']} - {row['code']}")
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)

    def _add(self, list_item: QListWidgetItem) -> None:
        row = list_item.data(Qt.UserRole)
        self.rows.append({"product_id": row["id"], "label": row["name"],
                          "quantity": self.quantity.value() * 1000})
        self.model.set_rows(self.rows)

    def _remove(self) -> None:
        current = self.table.selected_row()
        if current is not None and current in self.rows:
            self.rows.remove(current)
            self.model.set_rows(self.rows)

    def _save(self) -> None:
        result = self.services.route_notes.save(
            customer_id=self.customer.currentData(),
            driver_id=self.driver.currentData(),
            vehicle_id=self.vehicle.currentData(),
            departure=self.departure.text().strip(),
            destination=self.destination.text().strip(),
            km=self.km.value(),
            notes=self.doc.get("notes", ""),
            items=[{**row, "quantity": db_to_qty(row.get("quantity", 0))}
                   for row in self.rows],
            user_id=self.services.user_id,
            route_note_id=self.doc.get("id"))
        self.services.log("route.save", entity_type="route_note",
                          entity_id=result.get("id"), details=result.get("number", ""))
        self.accept()
