"""Cash register: sessions open/close with difference calculation, movement
journal and printable Z report."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QTabWidget, QVBoxLayout, QWidget)

from ...core.money import cents_to_money, format_money
from ...i18n import tr
from ...reporting import render
from ..dialogs.print_dialog import PrintDialog
from ..widgets.common import (DataTable, MoneySpin, TableModel, button, card, error,
                              info, label)
from .base import BaseScreen


class CashScreen(BaseScreen):
    module = "cash"
    subtitle = tr("cash.title")

    def build(self) -> None:
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)

        # -- session panel
        session_tab = QWidget()
        session_layout = QVBoxLayout(session_tab)
        self.session_card = card(tr("cash.session_current"))
        self.session_body = self.session_card.layout()
        session_layout.addWidget(self.session_card)
        self.session_actions = QHBoxLayout()
        self.open_button = button(tr("cash.session_open"), self._open_session,
                                  kind="success", icon="\U0001F4B0")
        self.close_button = button(tr("cash.session_close"), self._close_session,
                                   kind="danger")
        self.session_actions.addWidget(self.open_button)
        self.session_actions.addWidget(self.close_button)
        self.session_actions.addStretch(1)
        session_layout.addLayout(self.session_actions)
        self.tabs.addTab(session_tab, tr("cash.session_current"))

        # -- movements of the open session
        movements_tab = QWidget()
        mov_layout = QVBoxLayout(movements_tab)
        self.mov_model = TableModel([
            ("date", tr("common.date"), "datetime"),
            ("movement_type", tr("stock.movement_type"), "movement"),
            ("notes", tr("common.notes"), "text"),
            ("amount_cents", tr("common.amount"), "money"),
        ])
        self.mov_table = DataTable(self.mov_model, status_columns=())
        mov_layout.addWidget(self.mov_table, 1)
        bar = QHBoxLayout()
        bar.addWidget(button(tr("cash.deposit"), self._deposit, icon="\u2B06"))
        bar.addWidget(button(tr("cash.withdrawal"), self._withdrawal, icon="\u2B07"))
        bar.addStretch(1)
        mov_layout.addLayout(bar)
        self.tabs.addTab(movements_tab, tr("cash.movements"))

        # -- Z reports
        z_tab = QWidget()
        z_layout = QVBoxLayout(z_tab)
        self.z_model = TableModel([
            ("number", tr("cash.session"), "text"),
            ("opened_at", tr("cash.session_open"), "datetime"),
            ("closed_at", tr("cash.session_close"), "datetime"),
            ("opening_cents", tr("cash.opening_float"), "money"),
            ("counted_cents", tr("cash.counted"), "money"),
            ("closing_cents", tr("cash.expected"), "money"),
            ("difference_cents", tr("cash.difference"), "money"),
            ("status", tr("common.status"), "text"),
        ])
        self.z_table = DataTable(self.z_model, status_columns=())
        z_layout.addWidget(self.z_table, 1)
        z_layout.addWidget(button(tr("cash.z_report"), self._print_z, icon="\U0001F5A8"))
        self.tabs.addTab(z_tab, tr("cash.z_report"))
        super().build()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if not self._built:
            return
        session = self.services.cash.current_session()
        summary = self.services.cash.summary(session["id"]) if session else {}
        self._render_session(session, summary)
        self.open_button.setEnabled(not session)
        self.close_button.setEnabled(bool(session))
        self.mov_model.symbol = self.services.money_symbol()
        self.z_model.symbol = self.services.money_symbol()
        self.mov_model.set_rows(self.services.cash.movements())
        self.z_model.set_rows(self.services.cash.sessions())

    def _render_session(self, session: dict, summary: dict) -> None:
        body = self.session_body
        while body.count() > 1:
            item = body.takeAt(body.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        symbol = self.services.money_symbol()

        def money(cents):
            return format_money(cents_to_money(cents), symbol)

        holder = QWidget()
        layout = QVBoxLayout(holder)
        if not session:
            layout.addWidget(label(tr("pos.no_cash_session"), "CardTitle"))
        else:
            for line in (
                f"<b>{session['number']}</b>  -  {tr('cash.session_open')} : "
                f"{session['opened_at']}",
                f"{tr('cash.opening_float')} : <b>{money(summary['opening_cents'])}</b>",
                f"{tr('cash.cash_sales')} : <b>{money(summary['sales_cents'])}</b> "
                f"({summary['sales_count']} ventes)",
                f"{tr('cash.deposits')} : <b>{money(summary['deposits_cents'])}</b>",
                f"{tr('cash.withdrawals')} : <b>{money(summary['withdrawals_cents'])}</b>",
                f"{tr('expenses.title')} : <b>{money(summary['expenses_cents'])}</b>",
                f"{tr('payments.title')} : <b>{money(summary['payments_in_cents'] - summary['payments_out_cents'])}</b>",
                f"{tr('cash.expected')} : <b>{money(summary['theoretical_cents'])}</b>",
            ):
                layout.addWidget(label(line, "MoneyLabel"))
            methods = ", ".join(f"{m['method']}: {m['count']} = {money(m['total_cents']) if 'total_cents' in m else ''}"
                                for m in summary.get("by_method", []))
            if methods:
                layout.addWidget(label(methods, "HintLabel"))
        body.addWidget(holder)

    # ------------------------------------------------------------------
    def _open_session(self) -> None:
        if not self.require("create"):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("cash.session_open"))
        dialog.resize(360, 200)
        form = QFormLayout(dialog)
        amount = MoneySpin()
        form.addRow(tr("cash.opening_float"), amount)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.validate"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            session = self.services.cash.open_session(amount.cents(),
                                                      user_id=self.services.user_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.services.log("cash.session_open", entity_type="cash_session",
                          entity_id=session["id"], details=session["number"])
        self.refresh()

    def _close_session(self) -> None:
        session = self.services.cash.current_session()
        if not session:
            return
        if not self.require("validate"):
            return
        summary = self.services.cash.summary(session["id"])
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("cash.session_close"))
        dialog.resize(420, 280)
        form = QFormLayout(dialog)
        symbol = self.services.money_symbol()
        form.addRow(tr("cash.expected"), label(
            format_money(cents_to_money(summary["theoretical_cents"]), symbol), "MoneyLabel"))
        counted = MoneySpin()
        counted.setCents(summary["theoretical_cents"])
        form.addRow(tr("cash.counted"), counted)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.validate"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return
        result = self.services.cash.close_session(counted.cents(),
                                                  user_id=self.services.user_id)
        self.services.log("cash.session_close", entity_type="cash_session",
                          entity_id=session["id"],
                          details=f"{session['number']} diff="
                                  f"{result['difference_cents'] / 100}")
        if result["difference_cents"]:
            info(self, f"{tr('cash.difference')} : "
                       f"{format_money(cents_to_money(result['difference_cents']), symbol)}")
        self.refresh()

    def _deposit(self) -> None:
        self._movement("deposit")

    def _withdrawal(self) -> None:
        self._movement("withdrawal")

    def _movement(self, kind: str) -> None:
        if not self.require("create"):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(f"cash.{kind}s"))
        dialog.resize(380, 220)
        form = QFormLayout(dialog)
        amount = MoneySpin()
        form.addRow(tr("common.amount"), amount)
        reason = QLineEdit()
        form.addRow(tr("stock.reason"), reason)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button(tr("common.cancel"), dialog.reject))
        actions.addWidget(button(tr("common.save"), dialog.accept, kind="primary"))
        form.addRow(actions)
        if dialog.exec() != QDialog.Accepted or amount.cents() <= 0:
            return
        try:
            self.services.cash.add_movement(kind, amount.cents(), reason.text().strip(),
                                            user_id=self.services.user_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.services.log(f"cash.{kind}", entity_type="cash_movement",
                          details=f"{kind} {amount.cents() / 100}")
        self.refresh()

    # ------------------------------------------------------------------
    def _print_z(self) -> None:
        row = self.z_table.selected_row()
        session = self.services.db.fetch("cash_sessions", row["id"]) if row \
            else self.services.cash.current_session()
        if not session:
            info(self, tr("common.no_data"))
            return
        summary = self.services.cash.summary(session["id"])
        money = lambda cents: format_money(cents_to_money(cents),  # noqa: E731
                                           self.services.money_symbol())
        document = render.render_document(self.services, "receipt", {
            "number": session["number"],
            "date": (session.get("closed_at") or session["opened_at"])[:10],
            "kind": tr("cash.z_report"),
            "z_entries": [
                (tr("cash.opening_float"), summary["opening_cents"]),
                (tr("cash.cash_sales"), summary["sales_cents"]),
                (tr("cash.deposits"), summary["deposits_cents"]),
                (tr("cash.withdrawals"), -summary["withdrawals_cents"]),
                (tr("expenses.title"), -summary["expenses_cents"]),
                (tr("payments.title"), summary["payments_in_cents"] - summary["payments_out_cents"]),
                (tr("cash.expected"), summary["theoretical_cents"]),
                (tr("cash.difference"), summary["difference_cents"]),
            ],
            "items": [],
            "totals": {"total_ttc": cents_to_money(summary["theoretical_cents"]),
                       "total_ht": 0, "total_vat": 0, "subtotal_ht": 0},
        }, paper="thermal80")
        dialog = PrintDialog(self.services, document, paper="thermal80", parent=self)
        dialog.exec()
