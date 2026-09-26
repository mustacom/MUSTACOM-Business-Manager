"""Prestations de services: catalogue vendable au POS (17 types)."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLineEdit, QVBoxLayout

from ...core.crud import ValidationError
from ...i18n import tr
from ..widgets.common import FormGrid, MoneySpin, PercentSpin, button, error, scroll
from ..widgets.list_screen import ListScreen


class ServicesScreen(ListScreen):
    module = "services"
    subtitle = tr("services.title")
    export_name = "services"

    columns = [
        ("code", tr("common.code"), "text"),
        ("name", tr("common.designation"), "text"),
        ("category_name", tr("common.category"), "text"),
        ("price_cents", tr("products.sale_price"), "money"),
        ("cost_cents", tr("products.purchase_price"), "money"),
        ("vat_rate_bp", tr("products.vat"), "percent"),
        ("is_active", tr("common.active"), "bool"),
    ]

    def load_rows(self) -> list[dict]:
        rows = self.services.catalog.services()
        for row in rows:
            category = self.services.db.fetch("categories", row["category_id"]) \
                if row.get("category_id") else {}
            row["category_name"] = (category or {}).get("name", "")
        return rows

    def create_editor(self, row: dict | None) -> None:
        dialog = ServiceEditor(self.services, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.notify_change()

    def delete_row(self, row: dict) -> None:
        self.services.catalog.delete_service(row["id"])
        self.services.log("service.delete", entity_type="service", entity_id=row["id"],
                          details=row.get("name", ""))


class ServiceEditor(QDialog):
    def __init__(self, services, row: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.row = row or {}
        self.setWindowTitle(tr("services.new") if not row else tr("common.edit"))
        self.resize(640, 560)
        root = QVBoxLayout(self)
        form = FormGrid(columns=2)
        self.code = QLineEdit(self.row.get("code", ""))
        form.add(tr("common.code"), self.code)
        self.name = QLineEdit(self.row.get("name", ""))
        form.add(tr("common.designation"), self.name, required=True)
        self.category = QComboBox()
        self.category.addItem("", None)
        for category in services.catalog.categories(kind="service"):
            self.category.addItem(category["name"], category["id"])
        if self.row.get("category_id"):
            index = self.category.findData(self.row["category_id"])
            if index >= 0:
                self.category.setCurrentIndex(index)
        form.add(tr("common.category"), self.category)
        self.unit = QLineEdit(self.row.get("unit", "u"))
        form.add(tr("common.unit"), self.unit)
        self.price = MoneySpin()
        self.price.setCents(self.row.get("price_cents", 0))
        form.add(tr("products.sale_price"), self.price, required=True)
        self.cost = MoneySpin()
        self.cost.setCents(self.row.get("cost_cents", 0))
        form.add(tr("products.purchase_price"), self.cost)
        self.vat = PercentSpin()
        self.vat.setBp(self.row.get("vat_rate_bp", 2000))
        form.add(tr("products.vat"), self.vat)
        self.active = QCheckBox(tr("common.active"))
        self.active.setChecked(bool(self.row.get("is_active", 1)))
        form.add("", self.active)
        root.addWidget(scroll(form), 1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)

    def _save(self) -> None:
        data = {
            "code": self.code.text().strip(),
            "name": self.name.text().strip(),
            "category_id": self.category.currentData(),
            "unit": self.unit.text().strip() or "u",
            "price_cents": self.price.cents(),
            "cost_cents": self.cost.cents(),
            "vat_rate_bp": self.vat.bp(),
            "is_active": self.active.isChecked(),
        }
        try:
            self.services.catalog.save_service(data, service_id=self.row.get("id"),
                                               user_id=self.services.user_id)
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.services.log("service.save", entity_type="service",
                          entity_id=self.row.get("id"), details=data["name"])
        self.accept()
