"""Utilisateurs & rôles: comptes, rôles, matrice de permissions."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QScrollArea,
                               QVBoxLayout, QWidget)

from ...config import ACTIONS, MODULES
from ...core.crud import ValidationError
from ...i18n import tr
from ..widgets.common import (DataTable, TableModel, button, confirm, error, info,
                              label, scroll)
from ..widgets.list_screen import ListScreen

ROLE_CODES = ("admin", "manager", "cashier", "storekeeper", "technician", "accountant")


class UsersScreen(ListScreen):
    module = "users"
    subtitle = tr("users.title")
    export_name = "utilisateurs"

    columns = [
        ("username", tr("users.username"), "text"),
        ("full_name", tr("users.full_name"), "text"),
        ("role_code", tr("users.role"), "text"),
        ("email", tr("customers.email"), "text"),
        ("phone", tr("customers.phone"), "text"),
        ("last_login", tr("users.last_login"), "datetime"),
        ("is_active", tr("common.active"), "bool"),
    ]

    def load_rows(self) -> list[dict]:
        return self.services.auth.list_users()

    def build(self) -> None:
        super().build()
        self.root.insertWidget(1, self.toolbar(
            button(tr("users.role_permissions"), self._permissions, icon="\U0001F510"),
            button(tr("users.reset_password"), self._reset_password, icon="\U0001F511"),
            stretch=True))

    def create_editor(self, row: dict | None) -> None:
        dialog = UserEditor(self.services, row, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_row(self, row: dict) -> None:
        if row["username"] == self.services.username:
            error(self, tr("users.cannot_delete_self"))
            raise RuntimeError("blocked")
        self.services.auth.delete_user(row["id"])
        self.services.log("user.delete", entity_type="user", entity_id=row["id"],
                          details=row["username"])

    def _reset_password(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("edit"):
            return
        from PySide6.QtWidgets import QInputDialog

        password, ok = QInputDialog.getText(self, tr("users.reset_password"),
                                            tr("users.new_password"), QLineEdit.Password)
        if not ok or not password:
            return
        try:
            self.services.auth.set_password(row["id"], password)
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.services.log("user.password_reset", entity_type="user",
                          entity_id=row["id"], details=row["username"])
        info(self, tr("common.saved_ok"), tr("common.success"))

    def _permissions(self) -> None:
        dialog = PermissionsDialog(self.services, parent=self)
        dialog.exec()


class UserEditor(QDialog):
    def __init__(self, services, row: dict | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.row = row or {}
        self.setWindowTitle(tr("users.new") if not row else tr("common.edit"))
        self.resize(480, 420)
        form = QFormLayout(self)
        self.username = QLineEdit(self.row.get("username", ""))
        self.username.setReadOnly(bool(self.row))
        form.addRow(tr("users.username"), self.username)
        self.full_name = QLineEdit(self.row.get("full_name", ""))
        form.addRow(tr("users.full_name"), self.full_name)
        self.role = QComboBox()
        for code in ROLE_CODES:
            self.role.addItem(tr(f"role.{code}"), code)
        current = self.row.get("role_code", "cashier")
        index = self.role.findData(current)
        if index >= 0:
            self.role.setCurrentIndex(index)
        form.addRow(tr("users.role"), self.role)
        self.email = QLineEdit(self.row.get("email", ""))
        form.addRow(tr("customers.email"), self.email)
        self.phone = QLineEdit(self.row.get("phone", ""))
        form.addRow(tr("customers.phone"), self.phone)
        self.password = QLineEdit()
        self.password.setPlaceholderText(
            "" if self.row else tr("users.password_required"))
        form.addRow(tr("users.new_password") if self.row else tr("users.password"),
                    self.password)
        if self.row:
            self.active = QCheckBox(tr("common.active"))
            self.active.setChecked(bool(self.row.get("is_active", 1)))
            form.addRow("", self.active)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        form.addRow(actions)

    def _save(self) -> None:
        try:
            if self.row:
                self.services.auth.update_user(
                    self.row["id"], full_name=self.full_name.text().strip(),
                    email=self.email.text().strip(), phone=self.phone.text().strip(),
                    role_code=self.role.currentData(),
                    is_active=self.active.isChecked())
                if self.password.text():
                    self.services.auth.set_password(self.row["id"], self.password.text())
                self.services.log("user.update", entity_type="user",
                                  entity_id=self.row["id"], details=self.row["username"])
            else:
                if not self.password.text():
                    error(self, tr("users.password_required"))
                    return
                user_id = self.services.auth.create_user(
                    self.username.text().strip(), self.password.text(),
                    self.full_name.text().strip(), self.role.currentData(),
                    email=self.email.text().strip(), phone=self.phone.text().strip(),
                    created_by=self.services.user_id)
                self.services.log("user.create", entity_type="user", entity_id=user_id,
                                  details=self.username.text().strip())
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.accept()


class PermissionsDialog(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(tr("users.role_permissions"))
        self.resize(980, 640)
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.role = QComboBox()
        for code in ROLE_CODES:
            self.role.addItem(tr(f"role.{code}"), code)
        self.role.currentIndexChanged.connect(self._load)
        bar.addWidget(self.role)
        bar.addStretch(1)
        root.addLayout(bar)

        area = QScrollArea()
        area.setWidgetResizable(True)
        container = QWidget()
        self.grid = QGridLayout(container)
        area.setWidget(container)
        root.addWidget(area, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.close"), self.reject))
        actions.addWidget(button(tr("common.save"), self._save, kind="primary"))
        root.addLayout(actions)
        self.checks: dict[tuple[str, str], QCheckBox] = {}
        self._load()

    def _load(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.checks.clear()
        role_code = self.role.currentData()
        granted = self.services.auth.role_permissions(role_code)
        self.grid.addWidget(label(tr("common.module")), 0, 0)
        for column, action in enumerate(ACTIONS, start=1):
            self.grid.addWidget(label(tr(f"action.{action}")), 0, column)
        for row_index, module in enumerate(MODULES, start=1):
            self.grid.addWidget(label(tr(f"nav.{module}")), row_index, 0)
            for column, action in enumerate(ACTIONS, start=1):
                check = QCheckBox()
                check.setChecked((module, action) in granted)
                self.checks[(module, action)] = check
                self.grid.addWidget(check, row_index, column)

    def _save(self) -> None:
        role_code = self.role.currentData()
        granted = {key for key, check in self.checks.items() if check.isChecked()}
        self.services.auth.set_role_permissions(role_code, granted)
        self.services.log("role.permissions", entity_type="role",
                          details=f"{role_code}: {len(granted)} permissions")
        info(self, tr("common.saved_ok"), tr("common.success"))
        self.accept()
