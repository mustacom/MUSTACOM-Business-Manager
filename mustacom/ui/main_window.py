"""Main application window: sidebar, header, screen stack, status bar."""

from __future__ import annotations

import platform
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMenu, QMessageBox, QScrollArea, QStackedWidget,
                               QStatusBar, QVBoxLayout, QWidget)

from ..config import (APP_NAME, APP_SUPPORT_EMAIL, APP_VERSION, APP_WEBSITE,
                      EXPIRY_WARNING_DAYS)
from ..core.money import cents_to_money, format_money
from ..i18n import I18N, tr
from . import theme
from .navigation import NAVIGATION
from .widgets.common import button, confirm, error, icon, info


class Sidebar(QFrame):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("Sidebar")
        self.window = window
        self.setFixedWidth(232)
        self.buttons: dict[str, object] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        brand = QLabel(APP_NAME)
        brand.setObjectName("SidebarBrand")
        brand.setWordWrap(True)
        subtitle = QLabel("Gestion commerciale - Maroc")
        subtitle.setObjectName("SidebarSubtitle")
        subtitle.setContentsMargins(14, 0, 14, 12)
        outer.addWidget(brand)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        for group in NAVIGATION:
            group_label = QLabel(group.label_key and tr(group.label_key))
            group_label.setObjectName("SidebarGroup")
            group_label.setText(tr(group.label_key).upper())
            container_layout.addWidget(group_label)
            for item in group.items:
                action = QPushButton_with_icon(item.label, item.icon)
                action.setObjectName("NavButton")
                action.setCheckable(True)
                action.setCursor(Qt.PointingHandCursor)
                if item.shortcut:
                    action.setToolTip(f"{item.label}  ({item.shortcut})")
                action.clicked.connect(
                    lambda _checked=False, module=item.module: self.window.navigate(module))
                self.buttons[item.module] = action
                container_layout.addWidget(action)
        container_layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        self.footer = QLabel("")
        self.footer.setObjectName("SidebarFooter")
        self.footer.setWordWrap(True)
        outer.addWidget(self.footer)

    def select(self, module: str) -> None:
        for name, widget in self.buttons.items():
            widget.setChecked(name == module)

    def apply_permissions(self, session) -> None:
        for name, widget in self.buttons.items():
            widget.setVisible(session.has(name, "view"))

    def set_footer(self, text: str) -> None:
        self.footer.setText(text)


def QPushButton_with_icon(text: str, icon_name: str):
    """Nav button with a small drawn glyph on the left."""
    from PySide6.QtWidgets import QPushButton

    widget = QPushButton(f"   {text}")
    widget.setIcon(icon(icon_name, "#9FD4CF"))
    widget.setIconSize(QSize(16, 16))
    return widget


class MainWindow(QMainWindow):
    def __init__(self, services, session):
        super().__init__()
        self.services = services
        self.session = session
        self.screens: dict[str, QWidget] = {}
        self._current_module = ""
        self._license_checked_at: datetime | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(1180, 720)
        self.setWindowIcon(icon("shield"))

        self._build()
        self._build_menu()
        self._build_shortcuts()

        I18N.languageChanged.connect(self._on_language_changed)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(30_000)
        self._tick()

        QTimer.singleShot(0, lambda: self.navigate("dashboard"))

    # ------------------------------------------------------------------
    def _build(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(self)
        layout.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_header())

        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        layout.addWidget(right, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.sidebar.apply_permissions(self.session)
        self._refresh_header()

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("HeaderBar")
        bar.setFixedHeight(66)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(0)
        self.header_title = QLabel("")
        self.header_title.setObjectName("HeaderTitle")
        self.header_subtitle = QLabel("")
        self.header_subtitle.setObjectName("HeaderSubtitle")
        text.addWidget(self.header_title)
        text.addWidget(self.header_subtitle)
        layout.addLayout(text)
        layout.addStretch(1)

        self.session_label = QLabel("")
        self.session_label.setObjectName("UserChip")
        layout.addWidget(self.session_label)

        self.license_chip = QLabel("")
        self.license_chip.setObjectName("LicenseChip")
        self.license_chip.setCursor(Qt.PointingHandCursor)
        self.license_chip.mousePressEvent = lambda _e: self.navigate("license")
        layout.addWidget(self.license_chip)

        layout.addWidget(button("\u2630", self._toggle_sidebar, kind="ghost",
                                tooltip="Menu"))
        layout.addWidget(button("\u23FB", self._logout_menu, kind="ghost",
                                tooltip=tr("auth.logout")))
        return bar

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&Fichier")
        self._add_action(file_menu, tr("auth.change_password"), self._change_password)
        self._add_action(file_menu, tr("backup.now"), self._backup_now, "Ctrl+B")
        file_menu.addSeparator()
        self._add_action(file_menu, tr("auth.logout"), self.logout, "Ctrl+L")
        self._add_action(file_menu, tr("common.close"), self.close, "Ctrl+Q")

        tools_menu = menu_bar.addMenu("&Outils")
        self._add_action(tools_menu, tr("nav.barcode"), lambda: self.navigate("barcode"))
        self._add_action(tools_menu, tr("nav.backup"), lambda: self.navigate("backup"))
        self._add_action(tools_menu, tr("license.title"), lambda: self.navigate("license"))
        self._add_action(tools_menu, tr("nav.settings"), lambda: self.navigate("settings"))
        tools_menu.addSeparator()
        for code in ("fr", "ar", "en"):
            self._add_action(tools_menu, f"Langue : {I18N.language_name(code)}",
                             lambda _c=False, code=code: self._set_language(code))

        help_menu = menu_bar.addMenu("&Aide")
        self._add_action(help_menu, tr("common.about"), self._about, "F1")

    def _add_action(self, menu: QMenu, text: str, slot, shortcut: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_shortcuts(self) -> None:
        from .navigation import all_modules

        for group in NAVIGATION:
            for item in group.items:
                if not item.shortcut:
                    continue
                action = QAction(self)
                action.setShortcut(QKeySequence(item.shortcut))
                action.triggered.connect(
                    lambda _c=False, module=item.module: self.navigate(module))
                self.addAction(action)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def navigate(self, module: str) -> None:
        if not self.session.has(module, "view"):
            error(self, tr("common.permission_denied"), tr("common.warning"))
            return
        screen = self.screens.get(module)
        if screen is None:
            screen = self._create_screen(module)
            if screen is None:
                return
            self.screens[module] = screen
            self.stack.addWidget(screen)
        self.stack.setCurrentWidget(screen)
        self._current_module = module
        self.sidebar.select(module)
        if hasattr(screen, "ensure_built"):
            try:
                screen.ensure_built()
                screen.refresh()
            except Exception as exc:          # pragma: no cover - defensive
                self._show_screen_error(module, exc)
        self._set_header(module)
        self.statusBar().showMessage(tr("app.ready"), 4000)

    def _create_screen(self, module: str):
        from .registry import SCREENS

        factory = SCREENS.get(module)
        if factory is None:
            error(self, f"Module '{module}' indisponible", tr("common.error"))
            return None
        try:
            return factory(self.services, self)
        except Exception as exc:          # pragma: no cover - defensive
            self._show_screen_error(module, exc)
            return None

    def _show_screen_error(self, module: str, exc: Exception) -> None:
        import traceback

        traceback.print_exc()
        from .registry import PlaceholderScreen

        placeholder = PlaceholderScreen(self.services, self, module,
                                        f"{type(exc).__name__}: {exc}")
        placeholder.ensure_built()
        self.screens[module] = placeholder
        self.stack.addWidget(placeholder)

    def _set_header(self, module: str) -> None:
        from .navigation import module_label

        self.header_title.setText(module_label(module))
        screen = self.screens.get(module)
        subtitle = getattr(screen, "subtitle", "") or ""
        self.header_subtitle.setText(subtitle)

    def refresh_current(self) -> None:
        screen = self.stack.currentWidget()
        if screen is not None and hasattr(screen, "refresh"):
            screen.refresh()

    # ------------------------------------------------------------------
    # header / status
    # ------------------------------------------------------------------
    def _refresh_header(self) -> None:
        role = tr(f"users.role_{self.session.role_code}")
        self.session_label.setText(f"\U0001F464  {self.session.full_name}  \u00b7  {role}")

        status = self.services.license.status()
        if not status.active:
            self.license_chip.setText(tr("license.not_activated"))
            self.license_chip.setProperty("error", True)
        elif status.expired or status.blocked:
            self.license_chip.setText(tr("license.expired"))
            self.license_chip.setProperty("error", True)
        elif status.expiring_soon or status.in_grace:
            self.license_chip.setText(tr("license.expiring", days=max(0, status.days_left or 0)))
            self.license_chip.setProperty("warning", True)
        elif status.license_type == "trial":
            self.license_chip.setText(tr("license.trial_active", days=status.days_left or 0))
            self.license_chip.setProperty("warning", True)
        else:
            self.license_chip.setText(f"\u2713 {status.label}")
            self.license_chip.setProperty("error", False)
            self.license_chip.setProperty("warning", False)
        self.license_chip.style().unpolish(self.license_chip)
        self.license_chip.style().polish(self.license_chip)

        cash = self.services.cash.current_session()
        if cash:
            summary = self.services.cash.summary(cash["id"])
            self.sidebar.set_footer(
                f"Caisse ouverte\nSolde : {format_money(summary['theoretical_money'], self.services.money_symbol())}")
        else:
            self.sidebar.set_footer(f"{APP_WEBSITE}\n{APP_SUPPORT_EMAIL}")
        self.statusBar().showMessage(
            f"{tr('nav.dashboard')}  |  {datetime.now():%d/%m/%Y %H:%M}", 5000)

    def _tick(self) -> None:
        self._refresh_header()
        status = self.services.license.status()
        now = datetime.now()
        if status.blocked and (self._license_checked_at is None or
                               (now - self._license_checked_at).total_seconds() > 3600):
            self._license_checked_at = now
            QMessageBox.warning(self, tr("msg.license_required"), status.message)
        elif status.expiring_soon and self._license_checked_at is None:
            self._license_checked_at = now
            QMessageBox.information(
                self, tr("license.info"),
                tr("license.expiring", days=status.days_left or 0))

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _toggle_sidebar(self) -> None:
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _set_language(self, code: str) -> None:
        I18N.set_language(code)
        self.services.settings.set("locale.language", code, self.session.user_id)

    def _on_language_changed(self, _code: str) -> None:
        """Re-translate the sidebar and rebuild the visible screen."""
        for group in NAVIGATION:
            for item in group.items:
                widget = self.sidebar.buttons.get(item.module)
                if widget is not None:
                    widget.setText(f"   {item.label}")
        self._set_header(self._current_module)
        self._refresh_header()
        screen = self.stack.currentWidget()
        if screen is not None:
            self.stack.removeWidget(screen)
            self.screens.pop(self._current_module, None)
            screen.deleteLater()
        self.navigate(self._current_module or "dashboard")

    def _change_password(self) -> None:
        from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout

        from ..core.security import ValidationError

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("auth.change_password"))
        layout = QVBoxLayout(dialog)
        old = QLineEdit()
        old.setEchoMode(QLineEdit.Password)
        old.setPlaceholderText(tr("auth.old_password"))
        new = QLineEdit()
        new.setEchoMode(QLineEdit.Password)
        new.setPlaceholderText(tr("auth.new_password"))
        confirm_field = QLineEdit()
        confirm_field.setEchoMode(QLineEdit.Password)
        confirm_field.setPlaceholderText(tr("auth.confirm_password"))
        layout.addWidget(old)
        layout.addWidget(new)
        layout.addWidget(confirm_field)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.save"), dialog.accept, kind="primary"))
        layout.addLayout(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        if new.text() != confirm_field.text():
            error(self, tr("auth.password_mismatch"))
            return
        try:
            self.services.auth.change_password(self.session.user_id, old.text(), new.text())
        except ValidationError as exc:
            error(self, exc.message)
            return
        self.services.audit.record("user.password_change", user_id=self.session.user_id,
                                   username=self.session.username)
        info(self, tr("auth.password_changed"), tr("common.success"))

    def _backup_now(self) -> None:
        try:
            meta = self.services.backup.create(label="manuel")
        except Exception as exc:
            error(self, str(exc))
            return
        self.services.audit.record("backup.create", details=meta["name"])
        info(self, tr("backup.created", name=meta["name"]), tr("common.success"))

    def _logout_menu(self) -> None:
        if confirm(self, tr("auth.logout"), tr("auth.logout") + " ?"):
            self.logout()

    def logout(self) -> None:
        self.services.audit.record("logout", user_id=self.session.user_id,
                                   username=self.session.username)
        self.logged_out = True
        self.close()

    def _about(self) -> None:
        status = self.services.license.status()
        company = self.services.settings.company()
        QMessageBox.about(
            self, tr("common.about"),
            f"<h3>{APP_NAME}</h3>"
            f"<p>Version {APP_VERSION}</p>"
            f"<p><b>{company['company_name']}</b><br>"
            f"{company['company_address']}<br>"
            f"{company['company_zip']} {company['company_city']} - {company['company_country']}<br>"
            f"T\u00e9l : {company['company_phone']}<br>"
            f"{company['company_email']} - {company['company_website']}</p>"
            f"<p>Licence : <b>{status.label}</b>"
            + (f" - {tr('license.expires_on')} : {status.expires_at}" if status.expires_at
               else " - permanente")
            + f"<br>Poste : {status.machine_id}<br>Python {platform.python_version()}"
            f"</p>")

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if not getattr(self, "logged_out", False):
            if not confirm(self, tr("app.close_confirm"), tr("app.close_confirm_msg")):
                event.ignore()
                return
            self.services.audit.record("app.close", user_id=self.session.user_id,
                                       username=self.session.username)
        self.services.backup.stop_scheduler()
        self.services.db.close_all()
        event.accept()
