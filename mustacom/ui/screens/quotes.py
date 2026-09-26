"""Devis: list, editor, print/PDF, conversion to BC or facture, duplicate."""

from __future__ import annotations

from ...i18n import tr
from ..widgets.common import info
from .doc_base import DocListScreen


class QuotesScreen(DocListScreen):
    module = "quotes"
    subtitle = tr("quotes.title")
    service_attr = "quotes"
    render_kind = "quote"
    export_name = "devis"

    def extra_actions(self) -> list:
        return [
            (tr("common.print"), self.show_print, {"icon": "\U0001F5A8"}),
            (tr("common.export_pdf"), self.export_pdf, {"icon": "\U0001F4C4"}),
            (tr("quotes.to_order"), self._to_order, {"icon": "\u2192"}),
            (tr("quotes.to_invoice"), self._to_invoice, {"icon": "\u2192"}),
            (tr("quotes.duplicate"), self._duplicate, {"icon": "\u29C9"}),
            (tr("common.validate"), lambda: self.validate_selected("validated"),
             {"kind": "success"}),
        ]

    def _to_order(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("create"):
            return
        order = self.service().convert_to_order(row["id"], user_id=self.services.user_id)
        self.services.log("quote.convert_order", entity_type="quote",
                          entity_id=row["id"], details=order.get("number", ""))
        info(self, tr("quotes.converted", number=order.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()

    def _to_invoice(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("create"):
            return
        invoice = self.service().convert_to_invoice(row["id"],
                                                    user_id=self.services.user_id)
        self.services.log("quote.convert_invoice", entity_type="quote",
                          entity_id=row["id"], details=invoice.get("number", ""))
        info(self, tr("quotes.converted", number=invoice.get("number", "")),
             tr("common.success"))
        self.refresh()
        self.notify_change()

    def _duplicate(self) -> None:
        row = self.table.selected_row()
        if not row or not self.require("create"):
            return
        quote = self.service().duplicate(row["id"], user_id=self.services.user_id)
        self.services.log("quote.duplicate", entity_type="quote", entity_id=row["id"],
                          details=quote.get("number", ""))
        self.refresh()
        self.notify_change()
