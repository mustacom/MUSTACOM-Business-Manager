"""Generic CRUD list screen used by every catalogue module.

Subclasses declare the table model columns and override ``_create`` /
``_edit`` / ``_delete`` hooks.  Everything else - search, filters, refresh,
permission gating, CSV/Excel export buttons - is provided here once.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from ...i18n import tr
from ..widgets.common import (DataTable, SearchBox, TableModel, button, confirm,
                              error, hbox, label, vbox)
from ..screens.base import BaseScreen


class ListScreen(BaseScreen):
    columns: list[tuple[str, str, str]] = []
    search_keys: tuple[str, ...] = ("term",)
    export_name: str = "export"

    def build(self) -> None:
        self.filters: list[QComboBox] = []
        bar_items = []
        self.search = SearchBox(tr("common.search"))
        self.search.search.connect(self.refresh)
        bar_items.append(self.search)
        for spec in self.filter_specs():
            combo = QComboBox()
            combo.setMinimumWidth(150)
            combo.setProperty("filter_field", spec.get("field", ""))
            combo.addItem(tr("common.all"), "")
            for text, value in spec["options"]():
                combo.addItem(text, value)
            combo.currentIndexChanged.connect(lambda _i: self.refresh())
            self.filters.append(combo)
            bar_items.append(combo)
        bar_items.append(button(tr("common.refresh"), self.refresh, icon="\u21BB"))
        bar_items.append(button(tr("common.export_excel"), self._export_xlsx,
                                icon="\U0001F4E4"))
        bar_items.append(button(tr("common.export_csv"), self._export_csv,
                                icon="\U0001F4E4"))
        if self.can("delete"):
            bar_items.append(button(tr("common.delete"), self._delete_selected,
                                    kind="danger", icon="\U0001F5D1"))
        if self.can("edit"):
            bar_items.append(button(tr("common.edit"), self._edit_selected, icon="\u270E"))
        if self.can("create"):
            add = button(tr("common.new"), self._create_new, kind="primary", icon="+")
            bar_items.append(add)
        self.root.addWidget(self.toolbar(*bar_items))

        self.model = TableModel(self.columns)
        self.table = DataTable(self.model, status_columns=self.status_columns())
        self.table.doubleClickedRow.connect(self._on_double_click)
        self.root.addWidget(self.table, 1)

        self.count_label = label("", "HintLabel")
        self.root.addWidget(self.count_label)
        super().build()

    # -- hooks ----------------------------------------------------------
    def filter_specs(self) -> list[dict]:
        return []

    def status_columns(self) -> tuple[int, ...]:
        return ()

    def load_rows(self) -> list[dict]:
        raise NotImplementedError

    def _create_new(self) -> None:
        if not self.require("create"):
            return
        self.create_editor(None)

    def _edit_selected(self) -> None:
        if not self.require("edit"):
            return
        row = self.table.selected_row()
        if row:
            self.create_editor(row)

    def _delete_selected(self) -> None:
        if not self.require("delete"):
            return
        row = self.table.selected_row()
        if not row:
            return
        if not confirm(self, tr("common.confirm_delete"), tr("common.confirm_delete_msg"),
                       destructive=True):
            return
        try:
            self.delete_row(row)
        except Exception as exc:
            error(self, str(exc))
            return
        self.refresh()

    def _on_double_click(self, row: dict) -> None:
        if self.can("edit"):
            self.create_editor(row)

    def create_editor(self, row: dict | None) -> None:
        raise NotImplementedError

    def delete_row(self, row: dict) -> None:
        raise NotImplementedError

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        if not self._built:
            return
        self.model.symbol = self.services.money_symbol()
        rows = self.load_rows()
        term = self.search.text().strip().lower()
        if term:
            rows = [r for r in rows if term in " ".join(
                str(r.get(k, "")).lower() for k in self.search_fields())]
        for combo in self.filters:
            value = combo.currentData()
            if value not in (None, ""):
                field = combo.property("filter_field")
                rows = [r for r in rows if str(r.get(field)) == str(value)]
        self.model.set_rows(rows)
        self.count_label.setText(tr("common.rows", count=len(rows)))

    def search_fields(self) -> list[str]:
        return [c[0] for c in self.columns[:6]]

    # -- export ---------------------------------------------------------
    def _export_xlsx(self) -> None:
        self._export_impl("xlsx")

    def _export_csv(self) -> None:
        self._export_impl("csv")

    def _export_impl(self, kind: str) -> None:
        from PySide6.QtWidgets import QFileDialog

        suffix = "xlsx" if kind == "xlsx" else "csv"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("common.export"), str(self.services.paths.exports /
                                           f"{self.export_name}.{suffix}"),
            f"*.{suffix}")
        if not path:
            return
        from ...reporting.exporters import export_rows

        export_rows(path, self.columns, self.model.rows)
        from ..widgets.common import info

        info(self, tr("print.pdf_saved", path=path), tr("common.success"))
