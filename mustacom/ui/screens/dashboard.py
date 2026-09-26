"""Dashboard: KPI cards, turnover/profit charts, alerts and recent documents."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QLineSeries, QBarCategoryAxis, QValueAxis
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)  # noqa

from ...core.money import cents_to_money, format_money
from ...i18n import tr
from ..theme import ACCENT, DANGER, INFO, SUCCESS, WARNING
from ..widgets.common import (DataTable, TableModel, button, card, hbox, label,
                              stat_card, vbox)
from .base import BaseScreen

PERIODS = ("today", "week", "month", "year", "custom")


class DashboardScreen(BaseScreen):
    module = "dashboard"
    subtitle = ""

    def build(self) -> None:
        self.symbol = self.services.money_symbol()

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.period_combo = QComboBox()
        for key in PERIODS:
            self.period_combo.addItem(tr(f"common.{key}"), key)
        self.period_combo.setCurrentIndex(2)          # this month
        self.period_combo.currentIndexChanged.connect(self.refresh)
        filters.addWidget(label(tr("common.period") + " :", "FormLabel"))
        filters.addWidget(self.period_combo)
        filters.addWidget(label(tr("common.from") + " :", "FormLabel"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(lambda _d: self._on_custom())
        filters.addWidget(self.date_from)
        filters.addWidget(label(tr("common.to") + " :", "FormLabel"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(lambda _d: self._on_custom())
        filters.addWidget(self.date_to)
        filters.addStretch(1)
        filters.addWidget(button(tr("common.refresh"), self.refresh, icon="\u21BB"))
        self.root.addWidget(self.toolbar_from_layout(filters))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.grid = QVBoxLayout(content)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(12)
        scroll.setWidget(content)
        self.root.addWidget(scroll, 1)

        self.kpi_grid1 = QGridLayout()
        self.kpi_grid1.setSpacing(12)
        self.grid.addLayout(self.kpi_grid1)

        self.kpi_grid2 = QGridLayout()
        self.kpi_grid2.setSpacing(12)
        self.grid.addLayout(self.kpi_grid2)

        charts = QHBoxLayout()
        charts.setSpacing(12)
        self.sales_chart_frame = card(tr("dash.sales_graph"))
        self.profit_chart_frame = card(tr("dash.profit_graph"))
        charts.addWidget(self.sales_chart_frame, 3)
        charts.addWidget(self.profit_chart_frame, 2)
        self.grid.addLayout(charts)

        tables = QHBoxLayout()
        tables.setSpacing(12)
        self.top_model = TableModel([
            ("label", tr("products.designation"), "text"),
            ("quantity_display", tr("common.quantity"), "text"),
            ("revenue_money", tr("common.amount"), "amount"),
            ("profit_money", tr("dash.profit_estimated"), "amount"),
        ])
        self.top_table = DataTable(self.top_model)
        self.invoice_model = TableModel([
            ("number", tr("common.number"), "text"),
            ("date", tr("common.date"), "date"),
            ("customer_name", tr("customers.title"), "text"),
            ("total_cents", tr("common.total"), "money"),
            ("status", tr("common.status"), "status"),
        ])
        self.invoice_table = DataTable(self.invoice_model, status_columns=(4,))
        self.invoice_table.doubleClickedRow.connect(self._open_invoice)
        tables.addWidget(card(tr("dash.top_products"), content=self.top_table), 3)
        tables.addWidget(card(tr("dash.recent_invoices"), content=self.invoice_table), 3)
        self.grid.addLayout(tables)

        self.alert_card = card(tr("dash.alerts"))
        self.alert_card.setMaximumHeight(150)
        self.grid.addWidget(self.alert_card)
        self.grid.addStretch(1)
        super().build()

    def toolbar_from_layout(self, layout) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setLayout(layout)
        layout.setContentsMargins(10, 8, 10, 8)
        return bar

    # ------------------------------------------------------------------
    def _on_custom(self) -> None:
        if self.period_combo.currentData() != "custom":
            self.period_combo.blockSignals(True)
            self.period_combo.setCurrentIndex(len(PERIODS) - 1)
            self.period_combo.blockSignals(False)
        self.refresh()

    def period(self) -> tuple[str, str]:
        key = self.period_combo.currentData()
        today = date.today()
        if key == "today":
            start = end = today
        elif key == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        elif key == "month":
            start = today.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        elif key == "year":
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)
        else:
            start = self.date_from.date().toPython()
            end = self.date_to.date().toPython()
        if start > end:
            start, end = end, start
        return start.isoformat(), end.isoformat()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.symbol = self.services.money_symbol()
        self.top_model.symbol = self.symbol
        self.invoice_model.symbol = self.symbol
        date_from, date_to = self.period()
        db = self.services.db
        money = lambda cents: format_money(cents_to_money(cents), self.symbol)  # noqa: E731

        sales = self.services.sales.totals_for_period(date_from, date_to)
        today_sales = self.services.sales.totals_for_period(
            date.today().isoformat(), date.today().isoformat())
        expenses = self.services.expenses.total_for_period(date_from, date_to)
        purchases = int(db.scalar(
            "SELECT COALESCE(SUM(total_cents),0) FROM purchases WHERE date >= ? AND date <= ?",
            (date_from, date_to + " 23:59:59"), default=0))
        stock = self.services.stock.valuation()
        customers = int(db.scalar("SELECT COUNT(*) FROM customers WHERE is_active=1", default=0))
        suppliers = int(db.scalar("SELECT COUNT(*) FROM suppliers WHERE is_active=1", default=0))
        receivables = int(db.scalar(
            """SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM invoices
               WHERE status IN ('unpaid','partial') AND invoice_type <> 'proforma'""", default=0))
        payables = int(db.scalar(
            """SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM purchase_invoices
               WHERE status IN ('unpaid','partial')""", default=0))
        low = self.services.stock.low_stock()
        out = self.services.stock.low_stock(only_out=True)
        repairs_open = int(db.scalar(
            """SELECT COUNT(*) FROM repairs
               WHERE status NOT IN ('delivered','cancelled')""", default=0))

        profit_net = int(sales.get("profit_cents", 0)) - expenses

        self._fill_kpis(self.kpi_grid1, [
            stat_card(tr("dash.sales_today"), money(today_sales.get("turnover", 0)),
                      "\u20AC", color=ACCENT,
                      clickable=lambda: self.window.navigate("pos")),
            stat_card(tr("dash.sales_month"), money(sales.get("turnover", 0)),
                      "\U0001F4C8", color=ACCENT),
            stat_card(tr("dash.profit_estimated"), money(profit_net), "\U0001F4B0",
                      color=SUCCESS if profit_net >= 0 else DANGER),
            stat_card(tr("dash.sales_count"), f"{sales.get('count', 0)}", "\U0001F9FE",
                      color=INFO),
            stat_card(tr("dash.purchases_month"), money(purchases), "\U0001F4E6",
                      color=WARNING),
            stat_card(tr("dash.expenses_month"), money(expenses), "\U0001F4B8",
                      color=DANGER),
        ])
        self._fill_kpis(self.kpi_grid2, [
            stat_card(tr("dash.products_stock"), f"{stock.get('in_stock', 0)}",
                      "\U0001F4E6", color=INFO,
                      clickable=lambda: self.window.navigate("products")),
            stat_card(tr("dash.products_low"), f"{stock.get('low', 0)}", "\u26A0",
                      color=WARNING, clickable=lambda: self._show_stock("low")),
            stat_card(tr("dash.products_out"), f"{stock.get('out_of_stock', 0)}", "\u26D4",
                      color=DANGER, clickable=lambda: self._show_stock("out")),
            stat_card(tr("dash.customer_debts"), money(receivables), "\U0001F4B3",
                      color=DANGER if receivables else SUCCESS,
                      clickable=lambda: self.window.navigate("customers")),
            stat_card(tr("dash.supplier_debts"), money(payables), "\U0001F4C4",
                      color=DANGER if payables else SUCCESS,
                      clickable=lambda: self.window.navigate("suppliers")),
            stat_card(f"{tr('customers.title')} / {tr('suppliers.title')}",
                      f"{customers} / {suppliers}", "\U0001F465", color=INFO),
        ])

        self._draw_charts(date_from, date_to)

        top = self.services.sales.top_products(date_from, date_to, limit=8)
        self.top_model.set_rows(top)
        invoices = db.query(
            """SELECT i.*, c.name AS customer_name FROM invoices i
               LEFT JOIN customers c ON c.id = i.customer_id
               ORDER BY i.id DESC LIMIT 8""")
        self.invoice_model.set_rows([dict(r) for r in invoices])

        self._render_alerts(low, out, repairs_open, receivables, payables)
        self.subtitle = f"{date_from} \u2192 {date_to}"
        self.window._set_header(self.module)

    def _show_stock(self, stock_filter: str) -> None:
        self.window.navigate("products")
        screen = self.window.screens.get("products")
        if screen is not None and hasattr(screen, "set_stock_filter"):
            screen.set_stock_filter(stock_filter)

    @staticmethod
    def _discard(item) -> None:
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            return
        layout = item.layout()
        if layout is not None:
            while layout.count():
                DashboardScreen._discard(layout.takeAt(0))
            layout.deleteLater()

    def _fill_kpis(self, layout: QGridLayout, cards) -> None:
        while layout.count():
            self._discard(layout.takeAt(0))
        for index, widget in enumerate(cards):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumWidth(150)
            layout.addWidget(widget, index // 6, index % 6)
        for column in range(6):
            layout.setColumnStretch(column, 1)

    def _draw_charts(self, date_from: str, date_to: str) -> None:
        series = self._series_points(date_from, date_to)
        self._replace_chart(self.sales_chart_frame, self._line_chart(
            [p[0] for p in series], [float(p[1]) for p in series],
            tr("dash.sales_graph"), ACCENT))
        self._replace_chart(self.profit_chart_frame, self._line_chart(
            [p[0] for p in series], [float(p[2]) for p in series],
            tr("dash.profit_graph"), SUCCESS))

    def _series_points(self, date_from: str, date_to: str) -> list[tuple[str, float, float]]:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        days = max(1, (end - start).days + 1)
        raw = {row["day"]: row for row in self.services.sales.daily_series(days + 3)}
        points: list[tuple[str, float, float]] = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            row = raw.get(day)
            points.append((day[5:],
                           float(row["turnover"]) if row else 0.0,
                           float(row["profit"]) if row else 0.0))
        if len(points) > 31:                 # aggregate by week for long ranges
            weekly: list[tuple[str, float, float]] = []
            for index in range(0, len(points), 7):
                chunk = points[index:index + 7]
                weekly.append((chunk[0][0],
                               sum(p[1] for p in chunk),
                               sum(p[2] for p in chunk)))
            points = weekly
        return points

    def _line_chart(self, categories: list[str], values: list[float], title: str,
                    color: str) -> QChartView:
        chart = QChart()
        chart.legend().setVisible(False)
        chart.setBackgroundRoundness(8)
        series = QLineSeries()
        series.setColor(QColor(color))
        pen = QPen(QColor(color))
        pen.setWidth(3)
        series.setPen(pen)
        for index, value in enumerate(values):
            series.append(index, value)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append([c.split("-")[-1] for c in categories] or ["-"])
        axis_x.setLabelsColor(QColor("#64748B"))
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()  # noqa
        axis_y.setLabelFormat("%d")
        axis_y.setLabelsColor(QColor("#64748B"))
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(230)
        view.setStyleSheet("background: transparent; border: none;")
        return view

    def _replace_chart(self, frame: QFrame, view: QChartView) -> None:
        layout = frame.layout()
        while layout.count() > 1:
            self._discard(layout.takeAt(layout.count() - 1))
        layout.addWidget(view)

    def _render_alerts(self, low: list[dict], out: list[dict], repairs_open: int,
                       receivables: int, payables: int) -> None:
        layout = self.alert_card.layout()
        while layout.count() > 1:
            self._discard(layout.takeAt(layout.count() - 1))

        rows = QVBoxLayout()
        rows.setSpacing(6)
        money = lambda cents: format_money(cents_to_money(cents), self.symbol)  # noqa: E731
        alerts: list[tuple[str, str]] = []
        if out:
            alerts.append((DANGER, f"\u26D4 {len(out)} {tr('dash.products_out')} : "
                                   + ", ".join(p["sku"] for p in out[:6])))
        if low:
            alerts.append((WARNING, f"\u26A0 {len(low)} {tr('dash.products_low')} : "
                                    + ", ".join(p["sku"] for p in low[:6])))
        if repairs_open:
            alerts.append((INFO, f"\U0001F527 {repairs_open} {tr('repairs.title').lower()} "
                                 f"{tr('status.in_progress').lower()}"))
        if receivables:
            alerts.append((DANGER, f"\U0001F4B3 {tr('dash.customer_debts')} : "
                                   f"{money(receivables)}"))
        if payables:
            alerts.append((WARNING, f"\U0001F4C4 {tr('dash.supplier_debts')} : "
                                    f"{money(payables)}"))
        if not alerts:
            rows.addWidget(label("\u2705 " + tr("dash.no_alerts"), "HintLabel"))
        for color, text in alerts:
            row = QLabel(text)
            row.setStyleSheet(f"color: {color}; font-weight: 600; background: transparent;")
            row.setWordWrap(True)
            rows.addWidget(row)
        holder = QWidget()
        holder.setLayout(rows)
        layout.addWidget(holder)

    def _open_invoice(self, row: dict) -> None:
        self.window.navigate("invoices")
        screen = self.window.screens.get("invoices")
        if screen is not None and hasattr(screen, "select_invoice"):
            screen.select_invoice(row.get("id"))
