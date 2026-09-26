"""Shared machinery for every document module (devis, BC, BL, BR, factures).

``DocListScreen`` provides the grid + toolbar (new / edit / print / PDF /
validate / convert / delete) and ``DocEditorDialog`` the line editor used to
create or modify a document.  Concrete screens only declare which service,
render kind and conversion actions they expose.
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDateEdit, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from ...core.money import cents_to_money, format_money
from ...core.sales import CartItem
from ...i18n import tr
from ...reporting import render
from ..dialogs.print_dialog import PrintDialog
from ..widgets.common import (DataTable, PercentSpin, TableModel, button, confirm,
                              error, info, label, vbox)
from ..widgets.line_editor import LineEditor
from ..widgets.list_screen import ListScreen
from .base import BaseScreen


class DocListScreen(ListScreen):
    service_attr = ""          # e.g. "quotes"
    render_kind = ""           # e.g. "quote"
    party_table = "customers"  # or "suppliers"
    default_paper = "a4"
    editable_statuses = ("draft", "pending")

    columns = [
        ("number", tr("common.number"), "text"),
        ("date", tr("common.date"), "date"),
        ("party_name", tr("common.third_party"), "text"),
        ("total_cents", tr("common.total"), "money"),
        ("paid_cents", tr("common.paid"), "money"),
        ("status", tr("common.status"), "text"),
    ]

    def service(self):
        return getattr(self.services, self.service_attr)

    def build(self) -> None:
        super().build()
        extra_items = []
        for text, slot, kwargs in self.extra_actions():
            extra_items.append(button(text, slot, **kwargs))
        if extra_items:
            self.root.insertWidget(1, self.toolbar(*extra_items, stretch=True))

    def extra_actions(self) -> list:
        return []

    def status_columns(self) -> tuple[int, ...]:
        return (5,)

    def load_rows(self) -> list[dict]:
        rows = self.service().list(term=self.search.text().strip(), limit=2000)
        for row in rows:
            row["party_name"] = row.get("customer_name") or row.get("supplier_name") or ""
        return rows

    def refresh(self) -> None:
        if not self._built:
            return
        self.model.symbol = self.services.money_symbol()
        rows = self.load_rows()
        status = ""
        for combo in self.filters:
            if combo.currentData():
                status = combo.currentData()
        if status:
            rows = [r for r in rows if r.get("status") == status]
        self.model.set_rows(rows)
        self.count_label.setText(tr("common.rows", count=len(rows)))

    def filter_specs(self) -> list[dict]:
        return [{"field": "status", "options": lambda: [
            (tr(f"status.{code}"), code)
            for code in ("draft", "validated", "converted", "cancelled", "partial", "paid")]}]

    # ------------------------------------------------------------------
    def _selected_doc(self) -> dict | None:
        row = self.table.selected_row()
        if not row:
            return None
        return self.service().get(row["id"])

    def create_editor(self, row: dict | None) -> None:
        doc = self.service().get(row["id"]) if row else None
        if doc and doc.get("status") not in self.editable_statuses and \
                not self.can("validate"):
            error(self, tr("doc.not_editable"))
            return
        dialog = DocEditorDialog(self.services, self.service_attr, self.party_table,
                                 doc, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        doc = self.service().get(row["id"])
        if doc and doc.get("status") not in ("draft", "cancelled"):
            error(self, tr("doc.not_editable"))
            raise RuntimeError("blocked")
        self.service().delete(row["id"])
        self.services.log(f"{self.service_attr}.delete", entity_id=row["id"],
                          details=row.get("number", ""))

    # ------------------------------------------------------------------
    def _paper(self) -> str:
        return self.services.settings.get(f"print.paper_{self.render_kind}",
                                          self.default_paper) or self.default_paper

    def show_print(self, kind: str | None = None) -> None:
        doc = self._selected_doc()
        if not doc:
            return
        paper = self._paper()
        document = render.render_document(self.services, kind or self.render_kind,
                                          doc, paper)
        printer = self.services.settings.get("print.default_printer", "")
        dialog = PrintDialog(self.services, document, paper=paper,
                             default_printer=printer, parent=self)
        dialog.exec()

    def export_pdf(self) -> None:
        doc = self._selected_doc()
        if not doc:
            return
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, tr("common.export_pdf"),
            str(self.services.paths.exports / f"{doc['number']}.pdf"), "*.pdf")
        if not path:
            return
        paper = self._paper()
        document = render.render_document(self.services, self.render_kind, doc, paper)
        render.document_to_pdf(self.services, document, path, paper)
        info(self, tr("print.pdf_saved", path=path), tr("common.success"))

    def validate_selected(self, status: str = "validated") -> None:
        row = self.table.selected_row()
        if not row:
            return
        if not self.require("validate"):
            return
        self.service().set_status(row["id"], status, user_id=self.services.user_id)
        self.services.log(f"{self.service_attr}.validate", entity_id=row["id"],
                          details=f"{row['number']} -> {status}")
        self.refresh()
        self.notify_change()


class DocEditorDialog(QDialog):
    """Create / edit any header+lines document."""

    def __init__(self, services, service_attr: str, party_table: str,
                 doc: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.service_attr = service_attr
        self.party_table = party_table
        self.doc = doc or {}
        self.service = getattr(services, service_attr)
        title_map = {
            "quotes": tr("quotes.title"), "orders": tr("orders.title"),
            "invoices": tr("invoices.title"), "deliveries": tr("delivery.title"),
            "purchases": tr("purchases.title"),
        }
        self.setWindowTitle((title_map.get(service_attr, service_attr) + " - " +
                             (self.doc.get("number", "") or tr("common.new"))))
        self.resize(1000, 700)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.party = QComboBox()
        self.party.setMinimumWidth(280)
        table = "suppliers" if self.service_attr == "purchases" else self.party_table
        for party in self.services.catalog.parties(table):
            self.party.addItem(party["name"], party["id"])
        if self.doc.get("customer_id"):
            index = self.party.findData(self.doc["customer_id"])
            if index >= 0:
                self.party.setCurrentIndex(index)
        if self.doc.get("party_id") and self.service_attr == "orders":
            index = self.party.findData(self.doc["party_id"])
            if index >= 0:
                self.party.setCurrentIndex(index)
        if self.doc.get("supplier_id"):
            index = self.party.findData(self.doc["supplier_id"])
            if index >= 0:
                self.party.setCurrentIndex(index)
        header.addWidget(label(tr("customers.title") if table == "customers"
                               else tr("suppliers.title")))
        header.addWidget(self.party, 1)
        header.addWidget(label(tr("common.date")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        from PySide6.QtCore import QDate

        self.date.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        stamp = self.doc.get("date", "")
        if stamp:
            self.date.setDate(QDate.fromString(stamp[:10], "yyyy-MM-dd"))
        else:
            self.date.setDate(QDate.currentDate())
        header.addWidget(self.date)
        root.addLayout(header)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("pos.search_product"))
        self.search.textChanged.connect(self._results)
        search_row.addWidget(self.search, 2)
        self.results = QListWidget()
        self.results.setMaximumHeight(120)
        self.results.itemDoubleClicked.connect(self._add_result)
        root.addLayout(search_row)
        root.addWidget(self.results)

        readonly = bool(self.doc) and self.doc.get("status") not in ("draft", "pending")
        self.editor = LineEditor(self.services, readonly=readonly)
        if self.doc:
            from ...core.documents import items_to_cart

            self.editor.items = items_to_cart(self.doc.get("items", []), CartItem)
            self.editor.rebuild()
        root.addWidget(self.editor, 1)

        footer = QHBoxLayout()
        self.discount = PercentSpin()
        footer.addWidget(label(tr("pos.discount_percent")))
        footer.addWidget(self.discount)
        footer.addWidget(label(tr("common.notes")))
        self.notes = QLineEdit(self.doc.get("notes", ""))
        footer.addWidget(self.notes, 1)
        self.total_label = QLabel("")
        self.total_label.setObjectName("MoneyLabel")
        footer.addWidget(self.total_label)
        root.addLayout(footer)
        self.editor.linesChanged.connect(self._update_total)
        self._update_total()

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        self.save_button = button(tr("common.save"), self._save, kind="primary")
        if readonly:
            self.save_button.setEnabled(False)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

    def _update_total(self) -> None:
        totals = self.editor.totals(self.discount.value(), 0)
        self.total_label.setText(
            f"{tr('pos.total_ttc')} : "
            f"<b>{format_money(totals['total_ttc'], self.services.money_symbol())}</b>")

    def _results(self, term: str) -> None:
        self.results.clear()
        if not term.strip():
            return
        for row in self.services.sales.search(term, limit=15):
            item = QListWidgetItem(f"{row['name']}  -  {row['code']}")
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)

    def _add_result(self, list_item: QListWidgetItem) -> None:
        row = list_item.data(Qt.UserRole)
        source = self.services.db.fetch("products" if row["kind"] == "product"
                                        else "services", row["id"])
        cart_item = CartItem.from_product(source) if row["kind"] == "product" else \
            CartItem.from_service(source)
        self.editor.add_item(cart_item)

    # ------------------------------------------------------------------
    def _save(self) -> None:
        party_id = self.party.currentData()
        if not party_id:
            error(self, tr("common.required_fields"))
            return
        if not self.editor.items:
            error(self, tr("pos.empty_cart"))
            return
        date_str = self.date.date().toString("yyyy-MM-dd") + " " + \
            datetime.now().strftime("%H:%M:%S")
        discount_bp = int(self.discount.value() * 100)
        try:
            if self.service_attr == "quotes":
                result = self.service.save(
                    self.editor.items, customer_id=party_id, date=date_str,
                    notes=self.notes.text().strip(), discount_percent_bp=discount_bp,
                    user_id=self.services.user_id, quote_id=self.doc.get("id"))
            elif self.service_attr == "orders":
                result = self.service.save(
                    self.editor.items, party_id=party_id,
                    direction=self.doc.get("direction", "client"), date=date_str,
                    notes=self.notes.text().strip(), user_id=self.services.user_id,
                    order_id=self.doc.get("id"))
            elif self.service_attr == "invoices":
                result = self.service.save(
                    self.editor.items, customer_id=party_id, date=date_str,
                    invoice_type=self.doc.get("invoice_type", "standard"),
                    source_type=self.doc.get("source_type", ""),
                    source_id=self.doc.get("source_id"),
                    notes=self.notes.text().strip(), user_id=self.services.user_id,
                    invoice_id=self.doc.get("id"))
            elif self.service_attr == "purchases":
                result = self.service.save(
                    self.editor.items, supplier_id=party_id, date=date_str,
                    supplier_ref=self.doc.get("supplier_ref", ""),
                    notes=self.notes.text().strip(), user_id=self.services.user_id,
                    purchase_id=self.doc.get("id"))
            else:
                raise NotImplementedError(self.service_attr)
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.log(f"{self.service_attr}.save", entity_type=self.service_attr,
                          entity_id=result.get("id"), details=result.get("number", ""))
        self.accept()
