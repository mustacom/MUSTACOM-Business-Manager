"""Visual theme: professional ERP/POS look, light and dark variants.

Everything is plain QSS plus a small palette helper, so the same stylesheet
works on Windows, in the packaged EXE and in the headless test harness.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#0F766E"
ACCENT_DARK = "#0B5D57"
ACCENT_LIGHT = "#14B8A6"
DANGER = "#C0392B"
WARNING = "#D97706"
SUCCESS = "#15803D"
INFO = "#1D4ED8"

STATUS_COLORS = {
    "paid": SUCCESS, "validated": SUCCESS, "delivered": SUCCESS, "done": SUCCESS,
    "received": SUCCESS, "active": SUCCESS, "open": SUCCESS,
    "partial": WARNING, "partially_paid": WARNING, "in_progress": WARNING,
    "diagnosis": WARNING, "repairing": WARNING, "waiting_parts": WARNING,
    "draft": "#6B7280", "cancelled": DANGER, "expired": DANGER,
    "unpaid": DANGER, "inactive": "#6B7280",
    "sent": INFO, "confirmed": INFO, "accepted": INFO, "converted": INFO,
    "ordered": INFO, "invoiced": INFO, "closed": "#6B7280",
}

PALETTE_LIGHT = {
    "bg": "#F1F5F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "border": "#DDE3EA",
    "border_strong": "#C3CCD6",
    "text": "#0F172A",
    "text_muted": "#64748B",
    "sidebar": "#0B3B39",
    "sidebar_hover": "#12504C",
    "sidebar_active": "#0F766E",
    "sidebar_text": "#D7E6E4",
    "header": "#FFFFFF",
    "selection": "#CCFBF1",
}

PALETTE_DARK = {
    "bg": "#0E1418",
    "surface": "#161F25",
    "surface_alt": "#1B262D",
    "border": "#2A3941",
    "border_strong": "#3B4C56",
    "text": "#E6EDF3",
    "text_muted": "#8FA3AE",
    "sidebar": "#0A1A1C",
    "sidebar_hover": "#123033",
    "sidebar_active": "#0F766E",
    "sidebar_text": "#C9D8D6",
    "header": "#131C22",
    "selection": "#134E4A",
}


def palette(dark: bool = False) -> dict:
    return dict(PALETTE_DARK if dark else PALETTE_LIGHT)


def apply_palette(app: QApplication, dark: bool = False) -> None:
    colors = palette(dark)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(colors["bg"]))
    pal.setColor(QPalette.WindowText, QColor(colors["text"]))
    pal.setColor(QPalette.Base, QColor(colors["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(colors["surface_alt"]))
    pal.setColor(QPalette.Text, QColor(colors["text"]))
    pal.setColor(QPalette.Button, QColor(colors["surface"]))
    pal.setColor(QPalette.ButtonText, QColor(colors["text"]))
    pal.setColor(QPalette.Highlight, QColor(colors["sidebar_active"]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor(colors["surface"]))
    pal.setColor(QPalette.ToolTipText, QColor(colors["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(colors["text_muted"]))
    app.setPalette(pal)


def base_font(size: int = 10) -> QFont:
    families = [
        "Segoe UI",           # Windows default
        "Noto Sans",          # Linux with Noto
        "DejaVu Sans",
        "Noto Sans Arabic",   # Arabic fallback
        "Arial",
    ]
    available = set(QFontDatabase.families())
    for family in families:
        if family in available:
            font = QFont(family, size)
            font.setStyleStrategy(QFont.PreferAntialias)
            return font
    font = QFont()
    font.setPointSize(size)
    return font


def stylesheet(dark: bool = False) -> str:
    c = palette(dark)
    accent = ACCENT
    return f"""
* {{
    font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif;
    outline: none;
}}
QWidget {{
    background-color: {c['bg']};
    color: {c['text']};
    font-size: 10pt;
}}
QMainWindow, QDialog {{ background-color: {c['bg']}; }}

/* ---------------------------------------------------------- sidebar */
#Sidebar {{ background-color: {c['sidebar']}; border: none; }}
#Sidebar QLabel {{ background: transparent; color: {c['sidebar_text']}; border: none; }}
#SidebarBrand {{
    background-color: rgba(0,0,0,0.18);
    color: #FFFFFF; font-size: 12pt; font-weight: 700;
    padding: 16px 14px; border: none;
}}
#SidebarSubtitle {{ color: {ACCENT_LIGHT}; font-size: 8pt; font-weight: 600; }}
#SidebarGroup {{
    color: #7FA8A4; font-size: 7.5pt; font-weight: 700;
    padding: 12px 14px 4px 14px; background: transparent;
    letter-spacing: 1px;
}}
#NavButton {{
    background: transparent; color: {c['sidebar_text']};
    border: none; border-left: 3px solid transparent;
    padding: 9px 14px; text-align: left; font-size: 10pt;
}}
#NavButton:hover {{ background-color: {c['sidebar_hover']}; color: #FFFFFF; }}
#NavButton:checked, #NavButton[active="true"] {{
    background-color: {c['sidebar_active']}; color: #FFFFFF;
    border-left: 3px solid {ACCENT_LIGHT}; font-weight: 600;
}}
#SidebarFooter {{ background-color: rgba(0,0,0,0.22); color: #9DB8B5;
                  padding: 10px 14px; font-size: 8pt; border: none; }}

/* ---------------------------------------------------------- header */
#HeaderBar {{ background-color: {c['header']};
              border-bottom: 1px solid {c['border']}; }}
#HeaderTitle {{ font-size: 15pt; font-weight: 700; color: {c['text']}; background: transparent; }}
#HeaderSubtitle {{ font-size: 9pt; color: {c['text_muted']}; background: transparent; }}
#UserChip {{ background-color: {c['surface_alt']}; border: 1px solid {c['border']};
             border-radius: 14px; padding: 4px 12px; font-size: 9pt; }}
#LicenseChip {{ border-radius: 14px; padding: 4px 12px; font-size: 9pt; font-weight: 600;
                background-color: #ECFDF5; color: {SUCCESS}; border: 1px solid #A7F3D0; }}
#LicenseChip[warning="true"] {{ background-color: #FFFBEB; color: {WARNING};
                                border: 1px solid #FDE68A; }}
#LicenseChip[error="true"] {{ background-color: #FEF2F2; color: {DANGER};
                              border: 1px solid #FECACA; }}

/* ---------------------------------------------------------- cards */
#Card, QFrame#Card {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
#CardTitle {{ font-size: 10pt; font-weight: 700; color: {c['text']};
              background: transparent; padding: 2px 0; }}
#CardSubtitle {{ font-size: 8.5pt; color: {c['text_muted']}; background: transparent; }}
#StatValue {{ font-size: 13pt; font-weight: 700; background: transparent; }}
#StatLabel {{ font-size: 8.5pt; color: {c['text_muted']}; background: transparent; }}
#StatDelta {{ font-size: 8pt; background: transparent; }}
#StatIcon {{ background: transparent; border-radius: 8px; padding: 6px; }}

/* ---------------------------------------------------------- inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QDateEdit, QDateTimeEdit, QTimeEdit {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
    border: 1px solid {accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QDateEdit:disabled {{ background-color: {c['surface_alt']}; color: {c['text_muted']}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {DANGER}; background-color: #FEF2F2; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent;
                         border-right: 4px solid transparent;
                         border-top: 5px solid {c['text_muted']};
                         margin-right: 8px; }}
QComboBox QAbstractItemView {{
    background-color: {c['surface']}; border: 1px solid {c['border_strong']};
    selection-background-color: {accent}; selection-color: #FFFFFF; padding: 2px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}
QCalendarWidget QWidget {{ alternate-background-color: {c['surface_alt']}; }}

/* ---------------------------------------------------------- buttons */
QPushButton {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {c['surface_alt']}; border-color: {accent}; }}
QPushButton:pressed {{ background-color: {c['selection']}; }}
QPushButton:disabled {{ color: {c['text_muted']}; background-color: {c['surface_alt']}; }}
QPushButton#PrimaryButton, QPushButton[kind="primary"] {{
    background-color: {accent}; color: #FFFFFF; border: 1px solid {accent};
}}
QPushButton#PrimaryButton:hover, QPushButton[kind="primary"]:hover {{
    background-color: {ACCENT_DARK}; }}
QPushButton[kind="danger"] {{ background-color: {DANGER}; color: #FFFFFF;
                              border: 1px solid {DANGER}; }}
QPushButton[kind="danger"]:hover {{ background-color: #A93226; }}
QPushButton[kind="success"] {{ background-color: {SUCCESS}; color: #FFFFFF;
                               border: 1px solid {SUCCESS}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {accent}; }}
QPushButton[kind="ghost"]:hover {{ background-color: {c['surface_alt']}; }}
QPushButton#IconButton {{ background: transparent; border: none; padding: 4px 8px;
                          font-size: 11pt; }}
QPushButton#IconButton:hover {{ background-color: {c['surface_alt']};
                                border-radius: 6px; }}

/* ---------------------------------------------------------- tables */
QTableView, QTreeView, QListView {{
    background-color: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    gridline-color: {c['border']};
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
}}
QTableView::item, QTreeView::item {{ padding: 6px 8px; border: none; }}
QTableView::item:selected, QTreeView::item:selected {{
    background-color: {c['selection']}; color: {c['text']}; }}
QHeaderView::section {{
    background-color: {c['surface_alt']};
    color: {c['text_muted']};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {c['border']};
    border-right: 1px solid {c['border']};
    font-weight: 700; font-size: 9pt;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background-color: {c['surface_alt']}; border: none; }}
QTableView QTableCornerButton::section {{ background-color: {c['surface_alt']}; }}

/* ---------------------------------------------------------- tabs */
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px;
                    background-color: {c['surface']}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {c['text_muted']};
    padding: 8px 16px; border: none; border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}

/* ---------------------------------------------------------- scroll */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 5px;
                               min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 5px;
                                 min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------------------------------------------------------- misc */
QGroupBox {{
    border: 1px solid {c['border']}; border-radius: 8px;
    margin-top: 12px; padding: 12px 10px 10px 10px;
    font-weight: 700; background-color: {c['surface']};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                    color: {c['text_muted']}; }}
QStatusBar {{ background-color: {c['surface']}; border-top: 1px solid {c['border']};
              color: {c['text_muted']}; }}
QStatusBar::item {{ border: none; }}
QMenuBar {{ background-color: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
QMenuBar::item:selected {{ background-color: {c['selection']}; }}
QMenu {{ background-color: {c['surface']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {accent}; color: #FFFFFF; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QToolTip {{ background-color: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border_strong']}; padding: 5px 8px; }}
QProgressBar {{ background-color: {c['surface_alt']}; border: 1px solid {c['border']};
                border-radius: 5px; text-align: center; height: 12px; }}
QProgressBar::chunk {{ background-color: {accent}; border-radius: 4px; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px;
                                                 border: 1px solid {c['border_strong']};
                                                 background: {c['surface']}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent}; border-color: {accent}; }}
QSplitter::handle {{ background-color: {c['border']}; }}
QLabel#FormLabel {{ color: {c['text_muted']}; font-size: 9pt; font-weight: 600;
                    background: transparent; }}
QLabel#HintLabel {{ color: {c['text_muted']}; font-size: 8.5pt; background: transparent; }}
QLabel#ErrorLabel {{ color: {DANGER}; font-size: 9pt; font-weight: 600;
                     background: transparent; }}
QLabel#MoneyLabel {{ font-size: 13pt; font-weight: 700; background: transparent; }}
QFrame#Separator {{ background-color: {c['border']}; max-height: 1px; border: none; }}
QFrame#Toolbar {{ background-color: {c['surface']}; border: 1px solid {c['border']};
                  border-radius: 8px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---------------------------------------------------------- POS */
#PosCart {{ background-color: {c['surface']}; }}
#PosTotalBox {{ background-color: {c['sidebar']}; border-radius: 10px; }}
#PosTotalBox QLabel {{ color: #FFFFFF; background: transparent; }}
#PosTotalValue {{ font-size: 24pt; font-weight: 800; color: #FFFFFF; }}
#PosKeyHint {{ color: {c['text_muted']}; font-size: 8pt; background: transparent; }}
#ProductTile {{ background-color: {c['surface']}; border: 1px solid {c['border']};
                border-radius: 8px; }}
#ProductTile:hover {{ border: 1px solid {accent}; }}
#Badge {{ border-radius: 9px; padding: 2px 8px; font-size: 8pt; font-weight: 700; }}
"""


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#6B7280")


def install(app: QApplication, dark: bool = False) -> None:
    app.setFont(base_font())
    apply_palette(app, dark)
    app.setStyleSheet(stylesheet(dark))
