"""Sauvegarde: manuelle + auto, emplacement, vérification, restauration."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLineEdit, QSpinBox, QVBoxLayout, QWidget)

from ...i18n import tr
from ..widgets.common import (DataTable, TableModel, button, card, confirm, error,
                              info, label)
from .base import BaseScreen


class BackupScreen(BaseScreen):
    module = "backup"
    subtitle = tr("backup.title")

    def build(self) -> None:
        # settings card
        settings_card = card(tr("backup.settings"))
        form = QFormLayout()
        self.location = QLineEdit(self.services.settings.get("backup.location", ""))
        row = QHBoxLayout()
        row.addWidget(self.location, 1)
        row.addWidget(button("\U0001F4C1", self._pick_location))
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow(tr("backup.location"), wrap)
        self.auto_enabled = QCheckBox(tr("backup.auto_enabled"))
        self.auto_enabled.setChecked(self.services.settings.get_bool(
            "backup.auto_enabled", True))
        form.addRow("", self.auto_enabled)
        self.keep = QSpinBox()
        self.keep.setRange(1, 365)
        self.keep.setValue(self.services.settings.get_int("backup.keep", 30))
        form.addRow(tr("backup.keep"), self.keep)
        self.hour = QSpinBox()
        self.hour.setRange(0, 23)
        self.hour.setValue(self.services.settings.get_int("backup.hour", 20))
        form.addRow(tr("backup.hour"), self.hour)
        save = button(tr("common.save"), self._save_settings, kind="primary")
        form.addRow(save)
        settings_card.layout().addLayout(form)
        self.root.addWidget(settings_card)

        actions = QHBoxLayout()
        actions.addWidget(button(tr("backup.create"), self._create, kind="primary",
                                 icon="\U0001F4BE"))
        actions.addWidget(button(tr("backup.verify"), self._verify, icon="\u2705"))
        actions.addWidget(button(tr("backup.restore"), self._restore, kind="danger",
                                 icon="\u21A9"))
        actions.addWidget(button(tr("backup.prune"), self._prune, icon="\U0001F5D1"))
        actions.addWidget(button(tr("backup.integrity_report"), self._report,
                                 icon="\U0001F4CB"))
        actions.addStretch(1)
        self.root.addLayout(actions)

        self.model = TableModel([
            ("name", tr("backup.file"), "text"),
            ("label", tr("common.label"), "text"),
            ("size", tr("backup.size"), "text"),
            ("created_at", tr("common.date"), "datetime"),
        ])
        self.table = DataTable(self.model, status_columns=())
        self.root.addWidget(self.table, 1)
        super().build()

    def refresh(self) -> None:
        if not self._built:
            return
        self.model.set_rows(self.services.backup.list())

    # ------------------------------------------------------------------
    def _pick_location(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("backup.location"),
                                                self.location.text())
        if path:
            self.location.setText(path)

    def _save_settings(self) -> None:
        if not self.require("edit"):
            return
        self.services.settings.set_many({
            "backup.location": self.location.text().strip(),
            "backup.auto_enabled": self.auto_enabled.isChecked(),
            "backup.keep": self.keep.value(),
            "backup.hour": self.hour.value(),
        }, user_id=self.services.user_id)
        self.services.log("backup.settings", details=self.location.text().strip())
        info(self, tr("common.saved_ok"), tr("common.success"))

    def _create(self) -> None:
        if not self.require("create"):
            return
        try:
            result = self.services.backup.create("Manuelle",
                                                 mirror_to=self.location.text().strip()
                                                 or None)
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.log("backup.create", details=result.get("name", ""))
        info(self, tr("backup.created", name=result.get("name", "")), tr("common.success"))
        self.refresh()

    def _verify(self) -> None:
        row = self.table.selected_row()
        if not row:
            return
        ok, message = self.services.backup.verify(self.services.backup.location() /
                                                  row["name"])
        self.services.log("backup.verify", details=f"{row['name']} ok={ok}")
        if ok:
            info(self, tr("backup.verify_ok"), tr("common.success"))
        else:
            error(self, message)

    def _restore(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("delete"):
            return
        if not confirm(self, tr("backup.restore"), tr("backup.restore_confirm"),
                       destructive=True):
            return
        try:
            self.services.backup.restore(self.services.backup.location() / row["name"])
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.log("backup.restore", details=row["name"])
        info(self, tr("backup.restore_done"), tr("common.success"))

    def _prune(self) -> None:
        if not self.require("delete"):
            return
        removed = self.services.backup.prune()
        self.services.log("backup.prune", details=f"{removed} supprimées")
        info(self, tr("backup.pruned", count=removed), tr("common.success"))
        self.refresh()

    def _report(self) -> None:
        report = self.services.backup.integrity_report()
        info(self, "\n".join(f"{key} : {value}" for key, value in report.items()),
             tr("backup.integrity_report"))
