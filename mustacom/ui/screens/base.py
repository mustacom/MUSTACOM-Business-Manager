"""Base class for every module screen.

A screen is a plain ``QWidget`` that receives the :class:`Services` container
and the main window.  The main window creates screens lazily, calls
:meth:`BaseScreen.refresh` when the screen becomes visible, and asks
:meth:`BaseScreen.module` to decide whether the current user may see it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ...i18n import tr


class BaseScreen(QWidget):
    module = ""
    title = ""
    subtitle = ""
    icon = ""

    dataChanged = Signal()

    def __init__(self, services, window, parent=None):
        super().__init__(parent)
        self.services = services
        self.window = window
        self._built = False
        self._build_scaffold()

    # ------------------------------------------------------------------
    def _build_scaffold(self) -> None:
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(12)

    # -- lifecycle ----------------------------------------------------------
    def build(self) -> None:
        """Create the widgets once.  Subclasses override this."""
        self._built = True

    @property
    def content_layout(self) -> QVBoxLayout:
        return self.root

    def ensure_built(self) -> None:
        if not self._built:
            self.build()
            self._built = True

    def refresh(self) -> None:
        """Reload data.  Called every time the screen is shown."""

    def can(self, action: str = "view") -> bool:
        session = getattr(self.window, "session", None)
        if session is None:
            return True
        return session.has(self.module, action)

    def notify_change(self) -> None:
        self.dataChanged.emit()

    # -- helpers ------------------------------------------------------------
    def toolbar(self, *widgets, stretch: bool = True) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Toolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        for widget in widgets:
            if widget is not None:
                layout.addWidget(widget)
        if stretch:
            layout.addStretch(1)
        return bar

    def empty_hint(self, text: str = "") -> QLabel:
        hint = QLabel(text or tr("common.no_data"))
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("HintLabel")
        hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return hint

    def require(self, action: str, message: str = "") -> bool:
        if self.can(action):
            return True
        from ..widgets.common import error

        error(self, message or tr("common.permission_denied"), tr("common.warning"))
        return False
