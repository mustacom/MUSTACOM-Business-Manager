"""Reusable UI building blocks used by every screen."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from PySide6.QtCore import (QAbstractTableModel, QDate, QModelIndex, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QStyle,
                               QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QStyledItemDelegate, QTableView, QTextEdit, QVBoxLayout,
                               QWidget)

from ..theme import DANGER, SUCCESS, WARNING, status_color


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def tr(key: str, **kwargs) -> str:
    from ...i18n import I18N

    return I18N.tr(key, **kwargs)


def hbox(*widgets, spacing: int = 8, margin: int = 0, stretch_last: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margin, margin, margin, margin)
    for widget in widgets:
        if widget is None:
            continue
        layout.addWidget(widget)
    if stretch_last:
        layout.addStretch(1)
    return layout


def vbox(*widgets, spacing: int = 8, margin: int = 0) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margin, margin, margin, margin)
    for widget in widgets:
        if widget is None:
            continue
        layout.addWidget(widget)
    return layout


def label(text: str, object_name: str = "", word_wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    if word_wrap:
        widget.setWordWrap(True)
    return widget


def spacer() -> QWidget:
    widget = QWidget()
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return widget


def separator() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Separator")
    frame.setFrameShape(QFrame.HLine)
    frame.setFixedHeight(1)
    return frame


def button(text: str, slot=None, kind: str = "", icon: str = "",
           tooltip: str = "", shortcut: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if icon:
        widget.setText(f"{icon}  {text}")
    if tooltip:
        widget.setToolTip(tooltip)
    if shortcut:
        widget.setShortcut(shortcut)
    if slot is not None:
        widget.clicked.connect(slot)
    return widget


def card(title: str = "", subtitle: str = "", content: QWidget | None = None,
         object_name: str = "Card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    if title:
        layout.addWidget(label(title, "CardTitle"))
    if subtitle:
        layout.addWidget(label(subtitle, "CardSubtitle"))
    if content is not None:
        layout.addWidget(content)
    return frame


def stat_card(title: str, value: str, icon: str = "", delta: str = "",
              color: str = "", clickable: Callable | None = None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    if clickable is not None:
        frame.setCursor(Qt.PointingHandCursor)
        frame.setProperty("clickable", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)

    top = QHBoxLayout()
    top.setSpacing(10)
    if icon:
        badge = QLabel(icon)
        badge.setObjectName("StatIcon")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {color or '#0F766E'}22; color: {color or '#0F766E'};"
            f"border-radius: 8px; font-size: 14pt;")
        top.addWidget(badge)
    text_box = QVBoxLayout()
    text_box.setSpacing(2)
    text_box.addWidget(label(title, "StatLabel"))
    value_label = label(value, "StatValue")
    if color:
        value_label.setStyleSheet(f"color: {color};")
    text_box.addWidget(value_label)
    top.addLayout(text_box)
    top.addStretch(1)
    layout.addLayout(top)
    if delta:
        delta_label = label(delta, "StatDelta")
        delta_label.setStyleSheet(
            f"color: {SUCCESS if not delta.startswith('-') else DANGER};")
        layout.addWidget(delta_label)
    if clickable is not None:
        frame.mousePressEvent = lambda _event, cb=clickable: cb()  # type: ignore[assignment]
    return frame


def badge(text: str, color: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName("Badge")
    widget.setAlignment(Qt.AlignCenter)
    widget.setStyleSheet(
        f"background-color: {color or '#6B7280'}22; color: {color or '#6B7280'};"
        f"border-radius: 9px; padding: 2px 8px; font-size: 8pt; font-weight: 700;")
    return widget


def status_badge(status: str) -> QLabel:
    key = f"status.{status}"
    text = tr(key)
    return badge(text if text != key else str(status), status_color(status))


def payment_badge(method: str) -> QLabel:
    key = f"pay.{method}"
    text = tr(key)
    return badge(text if text != key else str(method), "#1D4ED8")


# ---------------------------------------------------------------------------
# form fields
# ---------------------------------------------------------------------------
class MoneySpin(QDoubleSpinBox):
    """Money entry displayed with 2 decimals and a space thousands separator."""

    def __init__(self, suffix: str = " DH", maximum: float = 999_999_999.0):
        super().__init__()
        self.setDecimals(2)
        self.setRange(-maximum, maximum)
        self.setSuffix(suffix)
        self.setGroupSeparatorShown(True)
        self.setMinimumWidth(130)

    def cents(self) -> int:
        return int(round(self.value() * 100))

    def setCents(self, cents: int | None) -> None:
        self.setValue(float(cents or 0) / 100.0)


class QtySpin(QDoubleSpinBox):
    def __init__(self, maximum: float = 9_999_999.0):
        super().__init__()
        self.setDecimals(3)
        self.setRange(-maximum, maximum)
        self.setMinimumWidth(90)
        self.setValue(1)

    def qty(self) -> Decimal:
        return Decimal(str(self.value()))

    def setQty(self, value) -> None:
        self.setValue(float(value or 0))


class PercentSpin(QDoubleSpinBox):
    def __init__(self, maximum: float = 100.0):
        super().__init__()
        self.setDecimals(2)
        self.setRange(0, maximum)
        self.setSuffix(" %")
        self.setMinimumWidth(90)

    def bp(self) -> int:
        return int(round(self.value() * 100))

    def setBp(self, value: int | None) -> None:
        self.setValue(float(value or 0) / 100.0)


class DateEdit(QDateEdit):
    def __init__(self, value: QDate | None = None, calendar: bool = True):
        super().__init__()
        self.setCalendarPopup(calendar)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setDate(value or QDate.currentDate())
        self.setMinimumWidth(120)

    def iso(self) -> str:
        return self.date().toString("yyyy-MM-dd")

    def setIso(self, value: str) -> None:
        if value:
            parsed = QDate.fromString(value[:10], "yyyy-MM-dd")
            if parsed.isValid():
                self.setDate(parsed)


class SearchBox(QLineEdit):
    """Search field that emits ``search`` 250 ms after the last keystroke."""

    search = Signal(str)

    def __init__(self, placeholder: str = ""):
        super().__init__()
        self.setPlaceholderText(placeholder or tr("common.search"))
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(220)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(lambda: self.search.emit(self.text().strip()))
        self.textChanged.connect(lambda _text: self._timer.start())
        self.returnPressed.connect(lambda: self.search.emit(self.text().strip()))


class FormGrid(QWidget):
    """Two-column label/field grid used by every editor form."""

    def __init__(self, columns: int = 2, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.layout_ = QGridLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setHorizontalSpacing(16)
        self.layout_.setVerticalSpacing(10)
        self._row = 0
        self._col = 0

    def add(self, caption: str, field: QWidget, span: int = 1,
            required: bool = False) -> QWidget:
        title = caption + (" *" if required else "")
        field_label = QLabel(title)
        field_label.setObjectName("FormLabel")
        self.layout_.addWidget(field_label, self._row, self._col * 2)
        self.layout_.addWidget(field, self._row, self._col * 2 + 1, 1, span * 2
                               if span > 1 else 1)
        if span > 1:
            self.layout_.setColumnStretch(self._col * 2 + 1, 1)
        self._col += span
        if self._col >= self.columns:
            self._col = 0
            self._row += 1
        return field

    def add_full(self, caption: str, field: QWidget) -> QWidget:
        field_label = QLabel(caption)
        field_label.setObjectName("FormLabel")
        self.layout_.addWidget(field_label, self._row, 0, 1, 2)
        self.layout_.addWidget(field, self._row + 1, 0, 1, self.columns * 2)
        self._row += 2
        self._col = 0
        return field

    def add_widget(self, widget: QWidget, span: int | None = None) -> None:
        self.layout_.addWidget(widget, self._row, 0, 1,
                               span or self.columns * 2)
        self._row += 1
        self._col = 0


# ---------------------------------------------------------------------------
# table model
# ---------------------------------------------------------------------------
class TableModel(QAbstractTableModel):
    """Simple read-only model driven by a list of dicts and a column spec.

    ``columns`` is a list of ``(key, header, kind)`` where kind controls
    formatting: ``text``, ``money``, ``qty``, ``date``, ``datetime``, ``int``,
    ``status``, ``percent``, ``bool``.
    """

    def __init__(self, columns: list[tuple[str, str, str]] | None = None, parent=None):
        super().__init__(parent)
        self._columns = columns or []
        self._rows: list[dict] = []
        self.symbol = "DH"

    # -- configuration ------------------------------------------------------
    def set_columns(self, columns: list[tuple[str, str, str]]) -> None:
        self.beginResetModel()
        self._columns = columns
        self.endResetModel()

    def column_kind(self, column: int) -> str:
        if 0 <= column < len(self._columns):
            return self._columns[column][2]
        return "text"

    def column_key(self, column: int) -> str:
        if 0 <= column < len(self._columns):
            return self._columns[column][0]
        return ""

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, index: int) -> dict:
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return {}

    def row_for_index(self, index: QModelIndex) -> dict:
        return self.row_at(index.row())

    @property
    def rows(self) -> list[dict]:
        return self._rows

    # -- Qt API -------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._columns):
            return self._columns[section][1]
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        key, _header, kind = self._columns[index.column()]
        row = self._rows[index.row()]
        value = row.get(key)
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return self.format(value, kind)
        if role == Qt.TextAlignmentRole:
            if kind in ("money", "qty", "int", "percent"):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            if kind in ("date", "datetime"):
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if kind == "status":
                return QColor(status_color(str(value or "")))
            if kind == "money":
                try:
                    if float(value or 0) < 0:
                        return QColor(DANGER)
                except (TypeError, ValueError):
                    pass
            if kind == "stock_state" and str(row.get(key)) in ("out", "low"):
                return QColor(DANGER if row.get(key) == "out" else WARNING)
        if role == Qt.FontRole and kind in ("status",):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.UserRole:
            return row
        return None

    def format(self, value: Any, kind: str) -> str:
        if value is None:
            return ""
        try:
            if kind == "money":
                from ...core.money import cents_to_money, format_money

                cents = value if isinstance(value, int) else int(float(value))
                return format_money(cents_to_money(cents), self.symbol)
            if kind == "amount":
                from ...core.money import format_money, to_decimal

                return format_money(to_decimal(value), self.symbol)
            if kind == "qty":
                from ...core.money import db_to_qty, format_qty

                return format_qty(int(value))
            if kind == "percent":
                return f"{float(value) / 100:.2f} %"
            if kind == "date":
                return str(value)[:10].replace("-", "/")
            if kind == "datetime":
                text = str(value).replace("T", " ")
                return text[:16].replace("-", "/")
            if kind == "status":
                text = tr(f"status.{value}")
                return value if text == f"status.{value}" else text
            if kind == "bool":
                return tr("common.yes") if value else tr("common.no")
            if kind == "payment":
                text = tr(f"pay.{value}")
                return value if text == f"pay.{value}" else text
            if kind == "movement":
                text = tr(f"mov.{value}")
                return value if text == f"mov.{value}" else text
        except (TypeError, ValueError):
            return str(value)
        return str(value)


class StatusDelegate(QStyledItemDelegate):
    """Paints status cells as coloured pills."""

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if bool(option.state & QStyle.StateFlag.State_Selected):
            painter.fillRect(option.rect, option.palette.highlight())
        text = index.data(Qt.DisplayRole) or ""
        raw = index.data(Qt.UserRole)
        model = index.model()
        status = ""
        if isinstance(raw, dict) and hasattr(model, "column_key"):
            status = str(raw.get(model.column_key(index.column()), ""))
        color = QColor(status_color(status or text))
        rect = option.rect.adjusted(4, 4, -4, -4)
        painter.setPen(QPen(color, 1))
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 38))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()


class DataTable(QTableView):
    """Table view pre-configured the way every screen wants it."""

    doubleClickedRow = Signal(dict)

    def __init__(self, model: TableModel | None = None, parent=None,
                 status_columns: tuple[int, ...] = ()):
        super().__init__(parent)
        self._model = model or TableModel()
        self.setModel(self._model)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setSortingEnabled(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        for column in status_columns:
            self.setItemDelegateForColumn(column, StatusDelegate(self))
        self.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index: QModelIndex) -> None:
        self.doubleClickedRow.emit(self._model.row_for_index(index))

    @property
    def model_(self) -> TableModel:
        return self._model

    def set_rows(self, rows: list[dict]) -> None:
        self._model.set_rows(rows)

    def selected_row(self) -> dict:
        indexes = self.selectionModel().selectedRows()
        if not indexes:
            return {}
        return self._model.row_for_index(indexes[0])

    def selected_id(self) -> int | None:
        row = self.selected_row()
        return row.get("id") if row else None

    def fit_columns(self, widths: dict[int, int]) -> None:
        for column, width in widths.items():
            self.setColumnWidth(column, width)


# ---------------------------------------------------------------------------
# scroll area helper
# ---------------------------------------------------------------------------
def scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    area.setFrameShape(QFrame.NoFrame)
    return area


def confirm(parent, title: str, message: str, destructive: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Warning if destructive else QMessageBox.Question)
    yes = box.addButton(tr("common.yes"), QMessageBox.YesRole)
    box.addButton(tr("common.no"), QMessageBox.NoRole)
    box.setDefaultButton(yes)
    box.exec()
    return box.clickedButton() is yes


def info(parent, message: str, title: str = "") -> None:
    QMessageBox.information(parent, title or tr("common.info"), message)


def error(parent, message: str, title: str = "") -> None:
    QMessageBox.critical(parent, title or tr("common.error"), message)


def ask_text(parent, title: str, prompt: str, default: str = "") -> str | None:
    from PySide6.QtWidgets import QInputDialog

    text, ok = QInputDialog.getText(parent, title, prompt, text=default)
    return text if ok else None


# ---------------------------------------------------------------------------
# icons (drawn at runtime so the packaged EXE needs no asset files)
# ---------------------------------------------------------------------------
ICON_CACHE: dict[str, QIcon] = {}


def icon(name: str, color: str = "#0F766E") -> QIcon:
    key = f"{name}:{color}"
    if key in ICON_CACHE:
        return ICON_CACHE[key]
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.save()
    draw_simple_glyph(painter, name, size)
    painter.restore()
    painter.end()
    ICON_CACHE[key] = QIcon(pixmap)
    return ICON_CACHE[key]


def draw_simple_glyph(painter: QPainter, name: str, size: int) -> None:
    from PySide6.QtCore import QPointF, QRectF

    margin = size * 0.22
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    center = QPointF(size / 2, size / 2)
    simple = {
        "dashboard": lambda: [painter.drawRect(rect)],
        "cart": lambda: [painter.drawRoundedRect(rect, 6, 6),
                        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())],
        "box": lambda: [painter.drawRoundedRect(rect, 4, 4),
                        painter.drawLine(rect.left(), center.y(), rect.right(), center.y())],
        "user": lambda: [painter.drawEllipse(QRectF(center.x() - 8, margin, 16, 16)),
                         painter.drawArc(rect.adjusted(2, 14, -2, -2), 0, -180 * 16)],
        "doc": lambda: [painter.drawRoundedRect(rect.adjusted(4, 0, -4, 0), 4, 4),
                        painter.drawLine(rect.left() + 12, center.y(), rect.right() - 12, center.y())],
        "chart": lambda: [painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom()),
                          painter.drawLine(rect.left() + 8, rect.bottom(), rect.left() + 8, rect.top() + 10),
                          painter.drawLine(rect.center().x(), rect.bottom(), rect.center().x(), rect.top() + 2),
                          painter.drawLine(rect.right() - 8, rect.bottom(), rect.right() - 8, rect.top() + 16)],
        "gear": lambda: [painter.drawEllipse(rect.adjusted(8, 8, -8, -8))],
        "key": lambda: [painter.drawEllipse(QRectF(rect.left(), center.y() - 8, 16, 16)),
                        painter.drawLine(rect.left() + 16, center.y(), rect.right(), center.y())],
        "shield": lambda: [painter.drawRoundedRect(rect.adjusted(4, 0, -4, -6), 10, 10)],
        "cash": lambda: [painter.drawRoundedRect(rect, 6, 6),
                         painter.drawEllipse(QRectF(center.x() - 6, center.y() - 6, 12, 12))],
        "truck": lambda: [painter.drawRoundedRect(QRectF(rect.left(), rect.top(), 22, 16), 3, 3),
                          painter.drawEllipse(QRectF(rect.left() + 2, rect.bottom() - 8, 8, 8)),
                          painter.drawEllipse(QRectF(rect.right() - 10, rect.bottom() - 8, 8, 8))],
        "wrench": lambda: [painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.top()),
                           painter.drawEllipse(QRectF(rect.right() - 14, rect.top(), 14, 14))],
        "backup": lambda: [painter.drawRoundedRect(rect.adjusted(2, 6, -2, -2), 4, 4),
                           painter.drawLine(center.x(), rect.top() + 6, center.x(), center.y() + 6)],
        "print": lambda: [painter.drawRoundedRect(rect.adjusted(2, 8, -2, -8), 3, 3),
                          painter.drawRect(QRectF(rect.left() + 6, rect.top(), 20, 10))],
    }
    action = simple.get(name, simple["doc"])
    action()
