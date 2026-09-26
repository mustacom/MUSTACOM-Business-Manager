"""Lightweight internationalisation with French / Arabic / English support.

A ``tr("key")`` style API is used everywhere in the UI layer.  Missing keys
fall back to the French table, then to the key itself, so the interface never
shows blank labels while translations are being completed.

Arabic flips the whole application to RTL through
``I18n.is_rtl`` / ``apply_layout_direction``.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QTranslator, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from .catalogs import CATALOGS

FALLBACK_LANG = "fr"


class I18n(QObject):
    """Singleton-ish translation manager."""

    languageChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang = FALLBACK_LANG
        self._qt_translator: QTranslator | None = None

    # -- state --------------------------------------------------------------
    @property
    def lang(self) -> str:
        return self._lang

    @property
    def catalog(self) -> dict:
        return CATALOGS.get(self._lang, {})

    @property
    def is_rtl(self) -> bool:
        return self._lang == "ar"

    @property
    def qt_locale(self) -> str:
        return {"fr": "fr_FR", "ar": "ar_MA", "en": "en_US"}[self._lang]

    def language_name(self, code: str | None = None) -> str:
        code = code or self._lang
        return {"fr": "Fran\u00e7ais", "ar": "\u0627\u0644\u0639\u0631\u0628\u064a\u0629",
                "en": "English"}.get(code, code)

    # -- translation --------------------------------------------------------
    def tr(self, key: str, **kwargs) -> str:
        text = self.catalog.get(key)
        if text is None:
            text = CATALOGS[FALLBACK_LANG].get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def set_language(self, lang: str) -> None:
        if lang not in CATALOGS:
            lang = FALLBACK_LANG
        if lang == self._lang:
            return
        self._lang = lang
        self._install_qt_translations()
        self.apply_layout_direction()
        self.languageChanged.emit(lang)

    def apply_layout_direction(self) -> None:
        from PySide6.QtCore import Qt

        direction = Qt.RightToLeft if self.is_rtl else Qt.LeftToRight
        app = QApplication.instance() or QGuiApplication.instance()
        if app is None:
            return
        app.setLayoutDirection(direction)
        for widget in app.allWidgets():
            widget.setLayoutDirection(direction)

    def _install_qt_translations(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
        translator = QTranslator(self)
        if translator.load(f"qtbase_{self._lang}", ":/qt/translations/"):
            app.installTranslator(translator)
        self._qt_translator = translator

    # -- helpers ------------------------------------------------------------
    def connect_all(self, refresh: Callable[[], None]) -> None:
        self.languageChanged.connect(lambda _lang: refresh())


I18N = I18n()


def tr(key: str, **kwargs) -> str:
    """Module level shortcut used across the UI."""
    return I18N.tr(key, **kwargs)


def rtl_stylesheet_adjustments() -> str:
    """Extra QSS applied only in RTL mode."""
    return """
    QTableView::item { padding-right: 6px; padding-left: 6px; }
    """
