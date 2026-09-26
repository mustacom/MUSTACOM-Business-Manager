"""Rapports: 18 états exportables en PDF / Excel / CSV."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QHBoxLayout,
                               QTabWidget, QVBoxLayout, QWidget)

from ...i18n import tr
from ...reporting import render
from ...reporting.exporters import export_rows, export_table_pdf
from ..widgets.common import (DataTable, TableModel, button, card, info, label)
from .base import BaseScreen


class ReportsScreen(BaseScreen):
    module = "reports"
    subtitle = tr("reports.title")

    def build(self) -> None:
        # period selector
        bar = QHBoxLayout()
        self.date_from = QDateEdit()
        self.date_to = QDateEdit()
        for widget in (self.date_from, self.date_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy")
            widget.setDateRange(QDate(2015, 1, 1), QDate(2040, 12, 31))
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_to.setDate(QDate.currentDate())
        bar.addWidget(label(tr("reports.period_from")))
        bar.addWidget(self.date_from)
        bar.addWidget(label(tr("reports.period_to")))
        bar.addWidget(self.date_to)
        self.report_choice = QComboBox()
        self.report_choice.setMinimumWidth(260)
        for name, _provider, _columns in self._definitions():
            self.report_choice.addItem(name)
        bar.addWidget(self.report_choice)
        bar.addWidget(button(tr("common.refresh"), self._run, kind="primary",
                             icon="\u21BB"))
        bar.addStretch(1)
        bar.addWidget(button(tr("common.export_pdf"), self._export_pdf,
                             icon="\U0001F4C4"))
        bar.addWidget(button(tr("common.export_excel"), self._export_xlsx,
                             icon="\U0001F4E4"))
        bar.addWidget(button(tr("common.export_csv"), self._export_csv,
                             icon="\U0001F4E4"))
        self.root.addLayout(bar)

        self.model = TableModel([])
        self.table = DataTable(self.model, status_columns=())
        self.root.addWidget(self.table, 1)
        self.summary = label("", "MoneyLabel")
        self.root.addWidget(self.summary)
        super().build()
        self._run()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if self._built:
            self._run()

    def _period(self) -> tuple[str, str]:
        return (self.date_from.date().toString("yyyy-MM-dd"),
                self.date_to.date().toString("yyyy-MM-dd"))

    def _definitions(self) -> list:
        s = self.services
        date_from, date_to = self._period() if self._built else ("", "")

        def sales_daily():
            rows = s.db.query(
                """SELECT substr(date,1,10) AS day, COUNT(*) AS count,
                          COALESCE(SUM(total_cents),0) AS total_cents,
                          COALESCE(SUM(total_ht_cents - cost_cents),0) AS profit_cents
                   FROM sales WHERE status='validated' AND date BETWEEN ? AND ?
                   GROUP BY day ORDER BY day""",
                (date_from, date_to + " 23:59:59"))
            return [dict(r) for r in rows]

        def sales_products():
            return s.sales.top_products(date_from, date_to, limit=500)

        def sales_categories():
            return s.sales.sales_by_category(date_from, date_to)

        def sales_methods():
            return s.sales.sales_by_payment_method(date_from, date_to)

        def margin():
            totals = s.sales.totals_for_period(date_from, date_to)
            expenses = s.expenses.total_for_period(date_from, date_to)
            return [{
                "label": tr("reports.turnover"), "value_cents": totals.get("turnover", 0)},
                {"label": tr("reports.margin"), "value_cents": totals["profit_cents"]},
                {"label": tr("expenses.title"), "value_cents": expenses},
                {"label": tr("reports.net_result"),
                 "value_cents": totals["profit_cents"] - expenses}]

        def top_customers():
            return [dict(r) for r in s.db.query(
                """SELECT c.name, COUNT(s.id) AS count,
                          COALESCE(SUM(s.total_cents),0) AS total_cents
                   FROM sales s JOIN customers c ON c.id = s.customer_id
                   WHERE s.status='validated' AND s.date BETWEEN ? AND ?
                   GROUP BY c.id ORDER BY total_cents DESC LIMIT 100""",
                (date_from, date_to + " 23:59:59"))]

        def customer_balances():
            return s.parties.balances(only_debtors=False)

        def supplier_balances():
            return s.parties.supplier_balances(only_creditors=False)

        def vat_report():
            rows = s.db.query(
                """SELECT COALESCE(SUM(total_vat_cents),0) AS collected
                   FROM invoices WHERE status IN ('paid','partial','unpaid')
                     AND invoice_type='standard' AND date BETWEEN ? AND ?""",
                (date_from, date_to + " 23:59:59"))
            collected = int(rows[0]["collected"]) if rows else 0
            deductible = int(s.db.scalar(
                """SELECT COALESCE(SUM(total_vat_cents),0) FROM purchase_invoices
                   WHERE date BETWEEN ? AND ?""",
                (date_from, date_to + " 23:59:59"), default=0))
            return [{"label": tr("reports.vat_collected"), "value_cents": collected},
                    {"label": tr("reports.vat_deductible"), "value_cents": deductible},
                    {"label": tr("reports.vat_due"), "value_cents": collected - deductible}]

        def purchases():
            return s.purchases.history(limit=2000)

        def supplier_invoices():
            rows = s.purchases.supplier_invoices()
            return [r for r in rows
                    if date_from <= str(r["date"])[:10] <= date_to]

        def expenses_by_category():
            return s.expenses.by_category(date_from, date_to)

        def stock_valuation():
            rows, _total = s.catalog.products(limit=10000)
            result = []
            from ...core.money import db_to_qty
            from decimal import Decimal

            for product in rows:
                qty = db_to_qty(product["stock"])
                result.append({
                    "sku": product["sku"], "name": product["name"],
                    "quantity": float(qty),
                    "value_cents": int(qty * Decimal(product["purchase_price_cents"]))})
            return result

        def stock_movements():
            return s.stock.movements(limit=5000, date_from=date_from, date_to=date_to)

        def stock_alerts():
            rows = s.stock.low_stock()
            for row in rows:
                from ...core.money import db_to_qty

                row["stock_display"] = f"{db_to_qty(row['stock']):g}"
                row["stock_min_display"] = f"{db_to_qty(row['stock_min']):g}"
            return rows

        def cash_daily():
            report = s.cash.daily_report(date_to)
            return [
                {"label": tr("reports.turnover"), "value_cents": report.get("total", 0)},
                {"label": tr("expenses.title"), "value_cents": report["expenses_cents"]},
                {"label": tr("payments.in"), "value_cents": report["payments_in_cents"]},
                {"label": tr("payments.out"), "value_cents": report["payments_out_cents"]},
                {"label": tr("reports.net_result"), "value_cents": report["net_cash_cents"]},
            ]

        def repairs_activity():
            activity = s.repairs.activity(date_from, date_to)
            return [{"status": tr(f"status.{status}"), "count": data["count"],
                     "total_cents": int(data["total"] * 100),
                     "deposits_cents": int(data["deposits"] * 100)}
                    for status, data in activity.items()]

        def audit():
            return [dict(r) for r in s.db.query(
                """SELECT timestamp, username, action, entity_type, details
                   FROM audit_logs WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY id DESC LIMIT 2000""",
                (date_from, date_to + " 23:59:59"))]

        return [
            (tr("reports.sales_daily"), sales_daily, [
                ("day", tr("common.date"), "date"), ("count", tr("pos.sales"), "int"),
                ("total_cents", tr("reports.turnover"), "money"),
                ("profit_cents", tr("reports.margin"), "money")]),
            (tr("reports.sales_products"), sales_products, [
                ("code", tr("common.code"), "text"), ("label", tr("common.label"), "text"),
                ("quantity", tr("common.quantity"), "qty"),
                ("revenue", tr("reports.turnover"), "money"),
                ("profit", tr("reports.margin"), "money")]),
            (tr("reports.sales_categories"), sales_categories, [
                ("category", tr("common.category"), "text"),
                ("quantity", tr("common.quantity"), "qty"),
                ("revenue", tr("reports.turnover"), "money")]),
            (tr("reports.sales_methods"), sales_methods, [
                ("payment_method", tr("pay.method"), "payment"), ("count", tr("pos.sales"), "int"),
                ("revenue", tr("common.total"), "money")]),
            (tr("reports.margin"), margin, [
                ("label", tr("common.label"), "text"),
                ("value_cents", tr("common.amount"), "money")]),
            (tr("reports.top_customers"), top_customers, [
                ("name", tr("customers.title"), "text"),
                ("count", tr("pos.sales"), "int"),
                ("total_cents", tr("reports.turnover"), "money")]),
            (tr("reports.customer_balances"), customer_balances, [
                ("code", tr("customers.code"), "text"),
                ("name", tr("common.name"), "text"),
                ("balance_cents", tr("customers.balance"), "money"),
                ("outstanding_cents", tr("customers.outstanding"), "money")]),
            (tr("reports.supplier_balances"), supplier_balances, [
                ("code", tr("suppliers.code"), "text"),
                ("name", tr("common.name"), "text"),
                ("balance_cents", tr("customers.balance"), "money"),
                ("outstanding_cents", tr("customers.outstanding"), "money")]),
            (tr("reports.vat"), vat_report, [
                ("label", tr("common.label"), "text"),
                ("value_cents", tr("common.amount"), "money")]),
            (tr("reports.purchases"), purchases, [
                ("date", tr("common.date"), "date"),
                ("purchase_number", tr("common.number"), "text"),
                ("supplier_name", tr("suppliers.title"), "text"),
                ("label", tr("common.label"), "text"),
                ("quantity", tr("common.quantity"), "qty"),
                ("line_total_cents", tr("common.total"), "money")]),
            (tr("reports.supplier_invoices"), supplier_invoices, [
                ("number", tr("common.number"), "text"),
                ("date", tr("common.date"), "date"),
                ("total_cents", tr("common.total"), "money"),
                ("paid_cents", tr("common.paid"), "money"),
                ("status", tr("common.status"), "text")]),
            (tr("reports.expenses_category"), expenses_by_category, [
                ("category", tr("common.category"), "text"),
                ("total_cents", tr("common.amount"), "money")]),
            (tr("reports.stock_valuation"), stock_valuation, [
                ("sku", tr("products.sku"), "text"), ("name", tr("common.name"), "text"),
                ("quantity", tr("common.quantity"), "amount"),
                ("value_cents", tr("products.value_ht"), "money")]),
            (tr("reports.stock_movements"), stock_movements, [
                ("date", tr("common.date"), "datetime"),
                ("sku", tr("products.sku"), "text"),
                ("product_name", tr("common.label"), "text"),
                ("movement_type", tr("stock.movement_type"), "movement"),
                ("quantity", tr("stock.delta"), "qty"),
                ("username", tr("audit.user"), "text")]),
            (tr("reports.stock_alerts"), stock_alerts, [
                ("sku", tr("products.sku"), "text"), ("name", tr("common.name"), "text"),
                ("stock_display", tr("products.stock"), "text"),
                ("stock_min_display", tr("products.stock_min"), "text"),
                ("supplier_name", tr("products.main_supplier"), "text")]),
            (tr("reports.cash_daily"), cash_daily, [
                ("label", tr("common.label"), "text"),
                ("value_cents", tr("common.amount"), "money")]),
            (tr("reports.repairs_activity"), repairs_activity, [
                ("status", tr("common.status"), "text"),
                ("count", tr("repairs.title"), "int"),
                ("total_cents", tr("common.total"), "money"),
                ("deposits_cents", tr("repairs.deposit"), "money")]),
            (tr("reports.audit"), audit, [
                ("timestamp", tr("common.date"), "datetime"),
                ("username", tr("audit.user"), "text"),
                ("action", tr("audit.action"), "text"),
                ("entity_type", tr("common.type"), "text"),
                ("details", tr("common.details"), "text")]),
        ]

    # ------------------------------------------------------------------
    def _current(self):
        definitions = self._definitions()
        index = self.report_choice.currentIndex()
        return definitions[index] if 0 <= index < len(definitions) else definitions[0]

    def _run(self) -> None:
        name, provider, columns = self._current()
        rows = provider()
        self.model.set_columns(columns)
        self.model.symbol = self.services.money_symbol()
        self.model.set_rows(rows)
        total = sum(int(row.get(columns[-1][0], 0) or 0) for row in rows
                    if columns[-1][2] == "money")
        from ...core.money import cents_to_money, format_money

        self.summary.setText(
            f"<b>{name}</b>  -  {tr('common.rows', count=len(rows))}"
            + (f"  -  {format_money(cents_to_money(total), self.services.money_symbol())}"
               if total else ""))

    def _export(self, kind: str) -> None:
        name, _provider, columns = self._current()
        suffix = {"pdf": "pdf", "xlsx": "xlsx", "csv": "csv"}[kind]
        path, _ = QFileDialog.getSaveFileName(
            self, tr("common.export"),
            str(self.services.paths.exports / f"rapport.{suffix}"), f"*.{suffix}")
        if not path:
            return
        title = f"{name}  ({self.date_from.date().toString('dd/MM/yyyy')} - " \
                f"{self.date_to.date().toString('dd/MM/yyyy')})"
        if kind == "pdf":
            export_table_pdf(title, columns, self.model.rows, path,
                             company_header=self.services.settings.company().get(
                                 "company_name", ""))
        else:
            export_rows(path, columns, self.model.rows)
        info(self, tr("print.pdf_saved", path=path), tr("common.success"))

    def _export_pdf(self) -> None:
        self._export("pdf")

    def _export_xlsx(self) -> None:
        self._export("xlsx")

    def _export_csv(self) -> None:
        self._export("csv")
