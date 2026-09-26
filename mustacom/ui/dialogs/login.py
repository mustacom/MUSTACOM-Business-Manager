"""Login dialog and the first-run administrator creation wizard."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout)

from ...config import APP_AUTHOR, APP_NAME, APP_VERSION, APP_WEBSITE
from ...core.security import ValidationError, password_strength
from ...i18n import I18N, tr
from ..widgets.common import button, error, label


class LoginDialog(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.session = None
        self.cancelled = False
        self._build()
        self._center()

    def _build(self) -> None:
        self.setWindowTitle(f"{tr('auth.login')} - {APP_NAME}")
        self.setModal(True)
        self.setFixedSize(430, 430)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(12)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 17pt; font-weight: 800; color: #0F766E;")
        subtitle = QLabel(f"{APP_AUTHOR} - {APP_WEBSITE}")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setObjectName("HintLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        form.addWidget(label(tr("auth.username"), "FormLabel"))
        self.username = QLineEdit()
        self.username.setPlaceholderText("admin")
        form.addWidget(self.username)

        form.addWidget(label(tr("auth.password"), "FormLabel"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022")
        form.addWidget(self.password)

        self.message = QLabel("")
        self.message.setObjectName("ErrorLabel")
        self.message.setWordWrap(True)
        self.message.hide()
        form.addWidget(self.message)

        self.submit = QPushButton(tr("auth.signin"))
        self.submit.setObjectName("PrimaryButton")
        self.submit.clicked.connect(self._submit)
        form.addWidget(self.submit)
        root.addWidget(card)

        self.password.returnPressed.connect(self._submit)
        self.username.returnPressed.connect(lambda: self.password.setFocus())

        footer = QLabel(f"v{APP_VERSION}")
        footer.setAlignment(Qt.AlignCenter)
        footer.setObjectName("HintLabel")
        root.addStretch(1)
        root.addWidget(footer)

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.center().x() - self.width() // 2,
                      geometry.center().y() - self.height() // 2)

    def _submit(self) -> None:
        try:
            self.session = self.services.auth.login(self.username.text().strip(),
                                                    self.password.text())
        except ValidationError as exc:
            self.message.setText(exc.message)
            self.message.show()
            self.password.selectAll()
            self.password.setFocus()
            return
        self.services.audit.record("login", user_id=self.session.user_id,
                                   username=self.session.username,
                                   entity_type="user", entity_id=self.session.user_id)
        self.accept()

    def reject(self) -> None:
        self.cancelled = True
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.cancelled = self.session is None
        super().closeEvent(event)


class FirstUserDialog(QDialog):
    """Shown once, on a brand-new database, to create the administrator."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.created = False
        self._build()

    def _build(self) -> None:
        self.setWindowTitle(tr("auth.first_user"))
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(12)

        title = QLabel(tr("auth.first_user"))
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        hint = QLabel(tr("auth.first_user_msg"))
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        form.addWidget(label(tr("auth.full_name"), "FormLabel"))
        self.full_name = QLineEdit("Administrateur")
        form.addWidget(self.full_name)

        form.addWidget(label(tr("auth.username"), "FormLabel"))
        self.username = QLineEdit("admin")
        form.addWidget(self.username)

        form.addWidget(label(tr("auth.password"), "FormLabel"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.textChanged.connect(self._strength)
        form.addWidget(self.password)

        self.strength = QLabel("")
        self.strength.setObjectName("HintLabel")
        form.addWidget(self.strength)

        form.addWidget(label(tr("auth.confirm_password"), "FormLabel"))
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        form.addWidget(self.confirm)

        form.addWidget(label(tr("settings.language"), "FormLabel"))
        self.language = QComboBox()
        for code in ("fr", "ar", "en"):
            self.language.addItem(I18N.language_name(code), code)
        form.addWidget(self.language)
        root.addWidget(card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), self.reject))
        create = QPushButton(tr("common.save"))
        create.setObjectName("PrimaryButton")
        create.clicked.connect(self._create)
        actions.addWidget(create)
        root.addLayout(actions)

    def _strength(self, text: str) -> None:
        score, name = password_strength(text)
        colors = ["#C0392B", "#C0392B", "#D97706", "#15803D", "#15803D"]
        self.strength.setText(f"{tr('auth.password')} : {name}")
        self.strength.setStyleSheet(f"color: {colors[score]};")

    def _create(self) -> None:
        if self.password.text() != self.confirm.text():
            error(self, tr("auth.password_mismatch"))
            return
        try:
            self.services.auth.create_user(self.username.text().strip(),
                                           self.password.text(),
                                           self.full_name.text().strip(),
                                           "admin")
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.services.settings.set("locale.language", self.language.currentData())
        self.services.audit.record("user.create", username=self.username.text().strip(),
                                   entity_type="user", details="administrateur initial")
        self.created = True
        self.accept()
