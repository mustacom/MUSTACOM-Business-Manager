"""Bons de livraison: editor with ordered/delivered quantities, mark
delivered, conversion to invoice."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout)

from ...core.money import db_to_qty, qty_to_db
from ...i18n import tr
from ..widgets.common import (DataTable, QtySpin, TableModel, button, error, info,
                              label)
from ..widgets.list_screen import ListScreen
from .base import BaseScreen
from .doc_base import DocListScreen


class DeliveryNotesScreen(DocListScreen):
    module = "delivery_notes"
    subtitle = tr("delivery.title")
    service_attr = "deliveries"
    render_kind = "delivery"
    export_name = "bons-livraison"

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
            (tr("delivery.to_invoice"), self._to_invoice, {"icon": "\u2192"}),
        ]

    def create_editor(self, row: dict | None) -> None:
        doc = self.service().get(row["id"]) if row else None
        dialog = DeliveryEditor(self.services, doc, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def _to_invoice(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("create"):
            return
        invoice = self.service().convert_to_invoice(row["id"],
                                                    user_id=self.services.user_id)
        self.services.log("delivery.convert_invoice", entity_type="delivery",
                          entity_id=row["id"], details=invoice.get("number", ""))
        info(self, tr("quotes.converted", number=invoice.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()


class DeliveryEditor(QDialog):
    def __init__(self, services, doc: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.doc = doc or {}
        self.setWindowTitle(tr("delivery.title") + " - " +
                            (self.doc.get("number", "") or tr("common.new")))
        self.resize(900, 640)
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        self.customer = QComboBox()
        self.customer.setMinimumWidth(260)
        for party in services.catalog.parties("customers"):
            self.customer.addItem(party["name"], party["id"])
        if self.doc.get("customer_id"):
            index = self.customer.findData(self.doc["customer_id"])
            if index >= 0:
                self.customer.setCurrentIndex(index)
        header.addWidget(label(tr("customers.title")))
        header.addWidget(self.customer, 1)
        header.addWidget(label(tr("delivery.address")))
        self.address = QLineEdit(self.doc.get("delivery_address", ""))
        header.addWidget(self.address, 1)
        root.addLayout(header)

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
            ("code", tr("products.sku"), "text"),
            ("label", tr("common.label"), "text"),
            ("ordered_qty", tr("delivery.ordered"), "qty"),
            ("delivered_qty", tr("delivery.delivered"), "qty"),
        ])
        self.table = DataTable(self.model, status_columns=())
        root.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.ordered = QtySpin()
        self.delivered = QtySpin()
        bar.addWidget(label(tr("delivery.ordered")))
        bar.addWidget(self.ordered)
        bar.addWidget(label(tr("delivery.delivered")))
        bar.addWidget(self.delivered)
        bar.addWidget(button(tr("common.apply"), self._apply))
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
        self.rows.append({"product_id": row["id"], "code": row["code"],
                          "label": row["name"], "unit": "u",
                          "ordered_qty": qty_to_db(self.ordered.qty() or 1),
                          "delivered_qty": qty_to_db(self.delivered.qty() or 1),
                          "unit_price_cents": row["price_cents"],
                          "vat_rate_bp": row.get("vat_rate_bp", 2000)})
        self.model.set_rows(self.rows)

    def _apply(self) -> None:
        current = self.table.selected_row()
        if not current:
            return
        for row in self.rows:
            if row is current:
                row["ordered_qty"] = qty_to_db(self.ordered.qty())
                row["delivered_qty"] = qty_to_db(self.delivered.qty())
        self.model.set_rows(self.rows)

    def _remove(self) -> None:
        current = self.table.selected_row()
        if current is not None and current in self.rows:
            self.rows.remove(current)
            self.model.set_rows(self.rows)

    def _save(self) -> None:
        if not self.rows:
            error(self, tr("pos.empty_cart"))
            return
        result = self.services.deliveries.save(
            [{**row, "ordered_qty": db_to_qty(row.get("ordered_qty", 0)),
              "delivered_qty": db_to_qty(row.get("delivered_qty", 0))}
             for row in self.rows],
            customer_id=self.customer.currentData(),
            delivery_address=self.address.text().strip(),
            source_type=self.doc.get("source_type", ""),
            source_id=self.doc.get("source_id"),
            user_id=self.services.user_id)
        self.services.log("delivery.save", entity_type="delivery",
                          entity_id=result.get("id"), details=result.get("number", ""))
        self.accept()
