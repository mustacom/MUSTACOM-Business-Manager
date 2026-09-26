"""Bons de commande client / fournisseur."""

from __future__ import annotations

from ...i18n import tr
from ..widgets.common import info
from .doc_base import DocListScreen


class OrdersScreen(DocListScreen):
    module = "orders"
    subtitle = tr("orders.title")
    service_attr = "orders"
    render_kind = "order_client"
    export_name = "commandes"

    def load_rows(self) -> list[dict]:
        rows = super().load_rows()
        for row in rows:
            if row.get("direction") == "supplier":
                row["party_name"] = row.get("supplier_name") or row.get("party_name", "")
        return rows

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
            (tr("orders.to_invoice"), self._to_invoice, {"icon": "\u2192"}),
            (tr("common.validate"), lambda: self.validate_selected("validated"),
             {"kind": "success"}),
        ]

    def show_print(self, kind: str | None = None) -> None:
        doc = self._selected_doc()
        if not doc:
            return
        render_kind = kind or ("order_supplier" if doc.get("direction") == "supplier"
                               else "order_client")
        super().show_print(render_kind)

    def _to_invoice(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("create"):
            return
        if row.get("direction") == "supplier":
            info(self, tr("orders.supplier_flow"))
            self.window.navigate("purchases")
            return
        invoice = self.service().convert_to_invoice(row["id"],
                                                    user_id=self.services.user_id)
        self.services.log("order.convert_invoice", entity_type="order",
                          entity_id=row["id"], details=invoice.get("number", ""))
        info(self, tr("quotes.converted", number=invoice.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()
