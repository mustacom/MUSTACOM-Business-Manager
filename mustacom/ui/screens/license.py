"""Licence: état, renouvellement, désactivation et générateur de clés
intégré (menu admin, conforme au choix client)."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QSpinBox, QTextEdit,
                               QVBoxLayout)

from ...core.license import (LICENSE_TYPES, export_license_file, issue_license,
                             machine_id)
from ...i18n import tr
from ..widgets.common import button, card, confirm, error, info, label, scroll
from .base import BaseScreen


class LicenseScreen(BaseScreen):
    module = "license"
    subtitle = tr("license.title")

    def build(self) -> None:
        body = QHBoxLayout()
        self.status_card = card(tr("license.current"))
        self.status_body = self.status_card.layout()
        left = QVBoxLayout()
        left.addWidget(self.status_card)
        actions = QHBoxLayout()
        actions.addWidget(button(tr("license.renew"), self._renew, kind="primary",
                                 icon="\U0001F504"))
        actions.addWidget(button(tr("license.deactivate"), self._deactivate,
                                 kind="danger"))
        actions.addStretch(1)
        left.addLayout(actions)
        body.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(button(tr("license.keygen"), self._keygen, kind="primary",
                               icon="\U0001F511"))
        right.addWidget(button(tr("license.export_file"), self._export_file,
                               icon="\U0001F4E4"))
        right.addWidget(button(tr("license.machine_id"), self._show_machine_id,
                               icon="\U0001F4BB"))
        right.addStretch(1)
        body.addLayout(right, 2)
        self.root.addLayout(body, 1)
        super().build()

    def refresh(self) -> None:
        if not self._built:
            return
        status = self.services.license.status()
        body = self.status_body
        while body.count() > 1:
            item = body.takeAt(body.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        holder = QVBoxLayout()
        if status.active:
            rows = [
                (tr("license.type"), tr(f"license.type_{status.license_type}")),
                (tr("settings.company_name"), status.company),
                (tr("license.user"), status.user),
                (tr("license.machine_id"), status.machine_id),
                (tr("license.serial"), status.key),
                (tr("license.activated_at"), status.activated_at[:19]),
                (tr("license.expires_at"),
                 status.expires_at[:10] if status.expires_at
                 else tr("license.permanent")),
                (tr("license.devices"), str(status.max_devices)),
            ]
            if status.days_left is not None:
                color = "#C0392B" if status.expiring_soon else "#15803D"
                rows.append((tr("license.days_left"),
                             f"<b style='color:{color}'>{status.days_left}</b>"))
            for name, value in rows:
                holder.addWidget(label(f"{name} : <b>{value}</b>", "MoneyLabel"))
        else:
            holder.addWidget(label(status.message or tr("license.not_activated"),
                                   "ErrorLabel"))
        body.addLayout(holder)

    # ------------------------------------------------------------------
    def _renew(self) -> None:
        if not self.require("edit"):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("license.renew"))
        dialog.resize(360, 200)
        form = QFormLayout(dialog)
        days = QSpinBox()
        days.setRange(1, 3650)
        days.setValue(365)
        form.addRow(tr("license.days"), days)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.validate"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        status = self.services.license.renew(days.value())
        self.services.log("license.renew", details=f"+{days.value()} jours")
        if not status.active:
            error(self, status.message or tr("license.renew_failed"))
            return
        info(self, tr("license.renewed"), tr("common.success"))
        self.refresh()

    def _deactivate(self) -> None:
        if not self.require("delete"):
            return
        if not confirm(self, tr("license.deactivate"), tr("license.deactivate_confirm"),
                       destructive=True):
            return
        self.services.license.deactivate()
        self.services.log("license.deactivate", details="licence désactivée")
        self.refresh()

    def _show_machine_id(self) -> None:
        info(self, f"{tr('license.machine_id')} : <b>{machine_id()}</b>",
             tr("license.title"))

    def _export_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("license.export_file"),
            str(self.services.paths.data / "mustacom-license.mlic"), "*.mlic")
        if not path:
            return
        status = self.services.license.status()
        if not status.active:
            error(self, tr("license.not_activated"))
            return
        import json

        row = self.services.license._row()
        from ...core.license import LicensePayload

        payload = LicensePayload(**json.loads(row["payload"]))
        signature = row["signature"]
        exported = export_license_file(payload, signature, path)
        info(self, tr("print.pdf_saved", path=str(exported)), tr("common.success"))

    # ------------------------------------------------------------------
    def _keygen(self) -> None:
        if not self.require("create"):
            return
        dialog = KeygenDialog(self.services, parent=self)
        dialog.exec()


class KeygenDialog(QDialog):
    """Générateur de clés intégré - réservé aux administrateurs."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(tr("license.keygen"))
        self.resize(560, 560)
        root = QVBoxLayout(self)
        root.addWidget(label(tr("license.keygen_warning"), "HintLabel"))
        form = QFormLayout()
        self.company = QLineEdit()
        form.addRow(tr("settings.company_name"), self.company)
        self.user = QLineEdit()
        form.addRow(tr("license.user"), self.user)
        self.machine = QLineEdit()
        form.addRow(tr("license.machine_id"), self.machine)
        self.license_type = QComboBox()
        for code in LICENSE_TYPES:
            self.license_type.addItem(tr(f"license.type_{code}"), code)
        self.license_type.setCurrentIndex(self.license_type.findData("professional"))
        form.addRow(tr("license.type"), self.license_type)
        self.duration = QSpinBox()
        self.duration.setRange(0, 36500)
        self.duration.setValue(365)
        self.duration.setSpecialValueText(tr("license.permanent"))
        form.addRow(tr("license.days"), self.duration)
        self.max_devices = QSpinBox()
        self.max_devices.setRange(1, 99)
        self.max_devices.setValue(1)
        form.addRow(tr("license.devices"), self.max_devices)
        root.addLayout(form)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output, 1)
        actions = QHBoxLayout()
        actions.addWidget(button(tr("license.generate"), self._generate, kind="primary"))
        actions.addWidget(button(tr("license.export_file"), self._export))
        actions.addStretch(1)
        actions.addWidget(button(tr("common.close"), self.reject))
        root.addLayout(actions)
        self._payload = None
        self._signature = ""

    def _generate(self) -> None:
        if not self.company.text().strip() or not self.machine.text().strip():
            error(self, tr("common.required_fields"))
            return
        payload, key, signature = issue_license(
            self.company.text().strip(), self.user.text().strip(),
            self.machine.text().strip().upper(), self.license_type.currentData(),
            duration_days=self.duration.value() or None,
            max_devices=self.max_devices.value())
        self._payload = payload
        self._signature = signature
        self.output.setPlainText(
            f"{tr('license.serial')} :\n\n{key}\n\n"
            f"{tr('license.expires_at')} : "
            f"{payload.expires_at or tr('license.permanent')}\n"
            f"{tr('license.machine_id')} : {payload.machine_id}\n"
            f"{tr('license.type')} : {payload.license_type}")
        self.services.log("license.keygen",
                          details=f"{payload.company} {payload.license_type}")

    def _export(self) -> None:
        if not self._payload:
            error(self, tr("license.generate_first"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("license.export_file"),
            f"{self.company.text().strip() or 'client'}.mlic", "*.mlic")
        if not path:
            return
        exported = export_license_file(self._payload, self._signature, path)
        info(self, tr("print.pdf_saved", path=str(exported)), tr("common.success"))
