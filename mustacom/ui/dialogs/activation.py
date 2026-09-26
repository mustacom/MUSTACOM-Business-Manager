"""ACTIVATION DU LOGICIEL - first-run license screen.

The screen offers four exits:

* activate with a serial key already registered on this machine,
* import the offline ``.mustacomlic`` file sent by MUSTACOM (main path),
* save a machine request the customer emails back,
* start the limited trial period.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from ...config import APP_NAME, APP_SUPPORT_EMAIL, APP_VERSION, LICENSE_FILE_EXT, TRIAL_DAYS
from ...core.license import machine_id
from ...i18n import I18N
from ...i18n import tr
from ..widgets.common import button, error, info, label


class ActivationDialog(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.activated = False
        self.quit_requested = False
        self._build()
        self._center()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(tr("activation.title"))
        self.setModal(True)
        self.setMinimumSize(620, 640)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(34, 26, 34, 22)
        root.setSpacing(14)

        title = QLabel(APP_NAME)
        title.setObjectName("HeaderTitle")
        title.setStyleSheet("font-size: 18pt; font-weight: 800; color: #0F766E;")
        subtitle = QLabel(tr("activation.title"))
        subtitle.setStyleSheet("font-size: 11pt; font-weight: 700;")
        hint = QLabel(tr("activation.subtitle"))
        hint.setObjectName("HintLabel")
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(hint)

        machine_box = QFrame()
        machine_box.setObjectName("Card")
        machine_layout = QVBoxLayout(machine_box)
        machine_layout.setContentsMargins(14, 12, 14, 12)
        machine_layout.setSpacing(6)
        machine_layout.addWidget(label(tr("activation.machine_id"), "FormLabel"))
        row = QHBoxLayout()
        self.machine_edit = QLineEdit(machine_id())
        self.machine_edit.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.machine_edit.setFont(font)
        row.addWidget(self.machine_edit)
        row.addWidget(button(tr("activation.copy_machine_id"), self._copy_machine_id,
                             icon="\u2398"))
        machine_layout.addLayout(row)
        root.addWidget(machine_box)

        form = QFrame()
        form.setObjectName("Card")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setSpacing(10)

        form_layout.addWidget(label(tr("activation.company"), "FormLabel"))
        self.company_edit = QLineEdit()
        self.company_edit.setPlaceholderText("MUSTACOM")
        form_layout.addWidget(self.company_edit)

        form_layout.addWidget(label(tr("activation.user"), "FormLabel"))
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Nom du responsable")
        form_layout.addWidget(self.user_edit)

        form_layout.addWidget(label(tr("activation.serial"), "FormLabel"))
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("MUST-XXXX-XXXX-XXXX-XXXX")
        self.key_edit.setFont(font)
        self.key_edit.textChanged.connect(self._format_key)
        form_layout.addWidget(self.key_edit)
        root.addWidget(form)

        actions = QHBoxLayout()
        activate = QPushButton(tr("activation.activate"))
        activate.setObjectName("PrimaryButton")
        activate.clicked.connect(self._activate)
        actions.addWidget(activate)
        actions.addWidget(button(tr("activation.offline"), self._import_license,
                                 icon="\u21E9"))
        actions.addWidget(button(tr("activation.request"), self._save_request,
                                 icon="\u2709"))
        actions.addStretch(1)
        root.addLayout(actions)

        trial_row = QHBoxLayout()
        trial_row.addWidget(button(tr("activation.trial", days=TRIAL_DAYS),
                                   self._start_trial, kind="ghost"))
        trial_row.addStretch(1)
        trial_row.addWidget(button(tr("common.close"), self._quit, kind="ghost"))
        root.addLayout(trial_row)

        footer = QLabel(
            f"{APP_NAME} v{APP_VERSION}  -  support : {APP_SUPPORT_EMAIL}\n"
            f"Poste : {machine_id()}   |   Langue : {I18N.language_name()}")
        footer.setObjectName("HintLabel")
        footer.setAlignment(Qt.AlignCenter)
        root.addStretch(1)
        root.addWidget(footer)

        self.key_edit.returnPressed.connect(self._activate)

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.center().x() - self.width() // 2,
                      geometry.center().y() - self.height() // 2)

    # ------------------------------------------------------------------
    def _format_key(self, text: str) -> None:
        from ...core.license import normalize_key

        cleaned = normalize_key(text)
        if cleaned and cleaned != text:
            self.key_edit.blockSignals(True)
            self.key_edit.setText(cleaned)
            self.key_edit.blockSignals(False)

    def _copy_machine_id(self) -> None:
        QGuiApplication.clipboard().setText(machine_id())
        info(self, tr("activation.machine_id") + f" : {machine_id()}",
             tr("common.success"))

    def _validate_inputs(self) -> bool:
        if not self.company_edit.text().strip() or not self.user_edit.text().strip():
            error(self, tr("activation.empty_fields"), tr("common.warning"))
            return False
        return True

    def _activate(self) -> None:
        if not self._validate_inputs():
            return
        status = self.services.license.activate(
            self.company_edit.text().strip(), self.user_edit.text().strip(),
            self.key_edit.text().strip())
        if status.blocked:
            error(self, status.message, tr("activation.invalid_key"))
            return
        self._finish()

    def _import_license(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("activation.import_license"), str(Path.home()),
            f"Licence MUSTACOM (*{LICENSE_FILE_EXT});;Tous les fichiers (*)")
        if not path:
            return
        status = self.services.license.activate_with_file(path)
        if status.blocked:
            error(self, status.message, tr("activation.license_file_invalid"))
            return
        self.company_edit.setText(status.company or self.company_edit.text())
        self.user_edit.setText(status.user or self.user_edit.text())
        self._finish()

    def _save_request(self) -> None:
        default = str(Path.home() / f"mustacom-demande-{machine_id()}.mustacomreq")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("activation.save_request"), default,
            "Demande de licence (*.mustacomreq)")
        if not path:
            return
        from ...core.license import export_machine_request

        saved = export_machine_request(path, self.company_edit.text().strip(),
                                       self.user_edit.text().strip())
        info(self, tr("activation.request_saved", path=str(saved)), tr("common.success"))

    def _start_trial(self) -> None:
        if not self._validate_inputs():
            return
        self.services.license.start_trial(self.company_edit.text().strip(),
                                          self.user_edit.text().strip())
        self._finish()

    def _finish(self) -> None:
        self.activated = True
        self.services.audit.record("license.activation",
                                   details=f"machine={machine_id()} "
                                           f"type={self.services.license.status().license_type}")
        self.accept()

    def _quit(self) -> None:
        self.quit_requested = True
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.quit_requested = not self.activated
        super().closeEvent(event)
