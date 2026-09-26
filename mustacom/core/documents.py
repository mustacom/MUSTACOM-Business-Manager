"""Document services: devis, bons de commande, bons de livraison, bons de
route, bons de retour, factures, avoirs, achats, paiements, d\u00e9penses, caisse
et r\u00e9parations.

All of them share the same header/lines shape, so :func:`write_lines` does the
line arithmetic once and every service stays thin and readable.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from ..db.database import Database, now_iso
from .money import (Line, cents_to_money, compute_totals, db_to_qty, money_to_cents,
                    qty_to_db, to_decimal)
from .numbering import Numbering
from .parties import PartyService
from .stock import StockService


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
ITEM_PARENT_COLUMN = {
    "sale_items": "sale_id",
    "quote_items": "quote_id",
    "order_items": "order_id",
    "invoice_items": "invoice_id",
    "credit_note_items": "credit_note_id",
    "repair_items": "repair_id",
    "purchase_items": "purchase_id",
    "return_items": "return_id",
    "delivery_items": "delivery_id",
}


def line_from_row(row: dict) -> Line:
    return Line(
        ref_type=row.get("ref_type", "product"),
        ref_id=row.get("product_id") or row.get("service_id"),
        code=row.get("code", ""), label=row.get("label", ""), unit=row.get("unit", "u"),
        qty=db_to_qty(row.get("quantity", 1000)),
        unit_price_ht=cents_to_money(row.get("unit_price_cents", 0)),
        vat_rate=Decimal(int(row.get("vat_rate_bp", 0))) / Decimal(100),
        discount_percent=Decimal(int(row.get("discount_percent_bp", 0))) / Decimal(100),
        discount_fixed=cents_to_money(row.get("discount_cents", 0)),
    )


def totals_from_rows(rows: list[dict], global_discount_percent=0,
                     global_discount_fixed=0) -> dict:
    return compute_totals([line_from_row(r) for r in rows],
                          to_decimal(global_discount_percent),
                          to_decimal(global_discount_fixed))


def write_lines(db: Database, table: str, parent_id: int, items, totals: dict) -> list[int]:
    """Persist document lines; ``items`` are CartItem-like objects."""
    column = ITEM_PARENT_COLUMN[table]
    prorated = totals.get("prorated_discount", {})
    ids: list[int] = []
    for index, item in enumerate(items):
        line = item.to_line()
        net_cents = money_to_cents(line.net_ht) - money_to_cents(
            prorated.get(index, Decimal(0)))
        vat_cents = int(round(net_cents * int(item.vat_rate_bp) / 10000))
        available = db.table_columns(table)
        row: dict = {
            column: parent_id,
            "code": item.code,
            "label": item.label,
            "unit": item.unit,
            "quantity": qty_to_db(item.qty),
            "unit_price_cents": int(item.unit_price_cents),
            "vat_rate_bp": int(item.vat_rate_bp),
            "line_ht_cents": net_cents,
            "line_vat_cents": vat_cents,
            "line_total_cents": net_cents + vat_cents,
            "sort_order": index,
        }
        if "ref_type" in available:
            row["ref_type"] = item.ref_type
        if "product_id" in available:
            row["product_id"] = item.ref_id if item.ref_type == "product" else None
        if "service_id" in available:
            row["service_id"] = item.ref_id if item.ref_type == "service" else None
        if "discount_percent_bp" in available:
            row["discount_percent_bp"] = int(item.discount_percent_bp)
        if "discount_cents" in available:
            row["discount_cents"] = money_to_cents(line.discount_amount) + money_to_cents(
                prorated.get(index, Decimal(0)))
        if "cost_cents" in available:
            row["cost_cents"] = int(item.cost_cents)
        if "delivered_qty" in available:
            row["delivered_qty"] = 0
        if "received_qty" in available:
            row["received_qty"] = 0
        ids.append(db.insert(table, **row))
    return ids


def lines_of(db: Database, table: str, parent_id: int) -> list[dict]:
    column = ITEM_PARENT_COLUMN[table]
    return [dict(r) for r in db.query(
        f"SELECT * FROM {table} WHERE {column} = ? ORDER BY sort_order, id", (parent_id,))]


def document_view(db: Database, header: dict, table: str) -> dict:
    items = lines_of(db, table, header["id"])
    header["items"] = items
    header["totals"] = {
        "subtotal_ht": cents_to_money(header.get("subtotal_cents", header.get("total_ht_cents", 0))),
        "total_ht": cents_to_money(header.get("total_ht_cents", 0)),
        "total_vat": cents_to_money(header.get("total_vat_cents", 0)),
        "total_ttc": cents_to_money(header.get("total_cents", 0)),
        "discount": cents_to_money(header.get("discount_cents", 0)),
        "paid": cents_to_money(header.get("paid_cents", 0)),
        "remaining": cents_to_money(int(header.get("total_cents", 0))
                                    - int(header.get("paid_cents", 0))),
    }
    breakdown: dict[str, int] = {}
    for item in items:
        rate = f"{Decimal(int(item.get('vat_rate_bp', 0))) / Decimal(100):.2f}"
        breakdown[rate] = breakdown.get(rate, 0) + int(item.get("line_vat_cents", 0))
    header["vat_breakdown"] = {rate: cents_to_money(c) for rate, c in sorted(breakdown.items())}
    return header


def items_to_cart(items: list[dict], cart_item_class):
    """Convert stored rows back into CartItem objects (for conversions)."""
    converted = []
    for row in items:
        converted.append(cart_item_class(
            ref_type=row.get("ref_type", "product"),
            ref_id=row.get("product_id") or row.get("service_id"),
            code=row.get("code", ""), label=row.get("label", ""), unit=row.get("unit", "u"),
            qty=db_to_qty(row.get("quantity", 1000)),
            unit_price_cents=int(row.get("unit_price_cents", 0)),
            vat_rate_bp=int(row.get("vat_rate_bp", 0)),
            discount_percent_bp=int(row.get("discount_percent_bp", 0)),
            discount_cents=int(row.get("discount_cents", 0)),
            cost_cents=int(row.get("cost_cents", 0)),
            track_stock=bool(row.get("product_id")),
        ))
    return converted


class BaseDocumentService:
    header_table = ""
    items_table = ""
    doc_type = ""
    party_column = "customer_id"

    def __init__(self, db: Database, numbering: Numbering, stock: StockService | None = None,
                 parties: PartyService | None = None):
        self.db = db
        self.numbering = numbering
        self.stock = stock
        self.parties = parties

    # -- reading ------------------------------------------------------------
    def get(self, doc_id: int) -> dict:
        header = self.db.fetch(self.header_table, doc_id)
        if not header:
            return {}
        party_id = header.get(self.party_column) or header.get("party_id")
        if party_id:
            table = "customers" if "customer" in (self.party_column or "") or \
                header.get("direction") in (None, "client") else "suppliers"
            if header.get("direction") == "supplier":
                table = "suppliers"
            header["party"] = self.db.fetch(table, party_id) or {}
        else:
            header["party"] = {}
        return document_view(self.db, header, self.items_table)

    def list(self, term: str = "", status: str = "", date_from: str = "", date_to: str = "",
             limit: int = 500) -> list[dict]:
        where = ["1=1"]
        params: list = []
        if term:
            where.append("d.number LIKE ?")
            params.append(f"%{term}%")
        if status:
            where.append("d.status = ?")
            params.append(status)
        if date_from:
            where.append("d.date >= ?")
            params.append(date_from)
        if date_to:
            where.append("d.date <= ?")
            params.append(date_to + " 23:59:59")
        clause = " AND ".join(where)
        columns = self.db.table_columns(self.header_table)
        select = "d.*"
        joins: list[str] = []
        if "customer_id" in columns:
            select += ", c.name AS customer_name"
            joins.append("LEFT JOIN customers c ON c.id = d.customer_id")
        elif "party_id" in columns:
            select += ", c.name AS customer_name, s.name AS supplier_name"
            joins.append("LEFT JOIN customers c ON c.id = d.party_id")
            joins.append("LEFT JOIN suppliers s ON s.id = d.party_id")
        if "supplier_id" in columns:
            select += ", s.name AS supplier_name"
            joins.append("LEFT JOIN suppliers s ON s.id = d.supplier_id")
        rows = self.db.query(
            f"SELECT {select} FROM {self.header_table} d "
            + " ".join(joins)
            + f" WHERE {clause} ORDER BY d.id DESC LIMIT ?", (*params, int(limit)))
        return [dict(r) for r in rows]

    def set_status(self, doc_id: int, status: str, user_id: int | None = None) -> None:
        self.db.update(self.header_table, doc_id, status=status)

    def delete(self, doc_id: int) -> None:
        self.db.execute(f"DELETE FROM {self.items_table} WHERE {ITEM_PARENT_COLUMN[self.items_table]} = ?",
                        (doc_id,))
        self.db.delete(self.header_table, doc_id)


# ---------------------------------------------------------------------------
# Devis
# ---------------------------------------------------------------------------
class QuoteService(BaseDocumentService):
    header_table = "quotes"
    items_table = "quote_items"
    doc_type = "devis"
    party_column = "customer_id"

    def save(self, items, *, customer_id: int, date: str = "", valid_days: int = 30,
             notes: str = "", terms: str = "", discount_percent_bp: int = 0,
             user_id: int | None = None, quote_id: int | None = None) -> dict:
        from .sales import cart_totals

        stamp = date or now_iso()
        totals = cart_totals(items, Decimal(discount_percent_bp) / 100)
        valid_until = (datetime.fromisoformat(stamp.replace(" ", "T")) +
                       timedelta(days=valid_days)).date().isoformat()
        with self.db.transaction():
            if quote_id:
                self.db.update("quotes", quote_id, date=stamp, valid_until=valid_until,
                               customer_id=customer_id,
                               subtotal_cents=totals["subtotal_ht_cents"],
                               discount_cents=totals["discount_cents"],
                               total_ht_cents=totals["total_ht_cents"],
                               total_vat_cents=totals["total_vat_cents"],
                               total_cents=totals["total_ttc_cents"], notes=notes, terms=terms)
                self.db.execute("DELETE FROM quote_items WHERE quote_id = ?", (quote_id,))
            else:
                quote_id = self.db.insert(
                    "quotes", number=self.numbering.next_number("devis", stamp), date=stamp,
                    valid_until=valid_until, customer_id=customer_id,
                    subtotal_cents=totals["subtotal_ht_cents"],
                    discount_cents=totals["discount_cents"],
                    total_ht_cents=totals["total_ht_cents"],
                    total_vat_cents=totals["total_vat_cents"],
                    total_cents=totals["total_ttc_cents"], notes=notes, terms=terms,
                    created_by=user_id, status="draft")
            write_lines(self.db, "quote_items", quote_id, items, totals)
        return self.get(quote_id)

    def duplicate(self, quote_id: int, user_id: int | None = None) -> dict:
        source = self.get(quote_id)
        if not source:
            return {}
        from .sales import CartItem

        items = items_to_cart(source["items"], CartItem)
        return self.save(items, customer_id=source["customer_id"],
                         notes=source.get("notes", ""), terms=source.get("terms", ""),
                         user_id=user_id)

    def convert_to_order(self, quote_id: int, user_id: int | None = None) -> dict:
        source = self.get(quote_id)
        if not source:
            return {}
        from .sales import CartItem

        items = items_to_cart(source["items"], CartItem)
        order = OrderService(self.db, self.numbering, self.stock, self.parties).save(
            items, party_id=source["customer_id"], direction="client",
            quote_id=quote_id, notes=source.get("notes", ""), user_id=user_id)
        self.db.update("quotes", quote_id, status="converted", converted_type="order",
                       converted_id=order["id"])
        return order

    def convert_to_invoice(self, quote_id: int, invoice_type: str = "standard",
                           user_id: int | None = None) -> dict:
        source = self.get(quote_id)
        if not source:
            return {}
        from .sales import CartItem

        items = items_to_cart(source["items"], CartItem)
        invoice = InvoiceService(self.db, self.numbering, self.stock, self.parties).save(
            items, customer_id=source["customer_id"], invoice_type=invoice_type,
            source_type="quote", source_id=quote_id, notes=source.get("notes", ""),
            user_id=user_id)
        self.db.update("quotes", quote_id, status="converted", converted_type="invoice",
                       converted_id=invoice["id"])
        return invoice


# ---------------------------------------------------------------------------
# Bons de commande (client + fournisseur)
# ---------------------------------------------------------------------------
class OrderService(BaseDocumentService):
    header_table = "orders"
    items_table = "order_items"
    doc_type = "bc_client"
    party_column = "party_id"

    def save(self, items, *, party_id: int, direction: str = "client", date: str = "",
             quote_id: int | None = None, expected_date: str = "", delivery_address: str = "",
             notes: str = "", terms: str = "", user_id: int | None = None,
             order_id: int | None = None) -> dict:
        from .sales import cart_totals

        stamp = date or now_iso()
        totals = cart_totals(items)
        doc_type = "bc_client" if direction == "client" else "bc_supplier"
        with self.db.transaction():
            if order_id:
                self.db.update("orders", order_id, date=stamp, party_id=party_id,
                               direction=direction, expected_date=expected_date,
                               delivery_address=delivery_address,
                               subtotal_cents=totals["subtotal_ht_cents"],
                               discount_cents=totals["discount_cents"],
                               total_ht_cents=totals["total_ht_cents"],
                               total_vat_cents=totals["total_vat_cents"],
                               total_cents=totals["total_ttc_cents"], notes=notes, terms=terms)
                self.db.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            else:
                order_id = self.db.insert(
                    "orders", number=self.numbering.next_number(doc_type, stamp), date=stamp,
                    direction=direction, party_id=party_id, quote_id=quote_id,
                    expected_date=expected_date, delivery_address=delivery_address,
                    subtotal_cents=totals["subtotal_ht_cents"],
                    discount_cents=totals["discount_cents"],
                    total_ht_cents=totals["total_ht_cents"],
                    total_vat_cents=totals["total_vat_cents"],
                    total_cents=totals["total_ttc_cents"], notes=notes, terms=terms,
                    created_by=user_id, status="draft")
            write_lines(self.db, "order_items", order_id, items, totals)
        return self.get(order_id)

    def mark_delivered(self, order_id: int, delivered_map: dict[int, Any]) -> None:
        """Update delivered quantities and derive the order status."""
        items = lines_of(self.db, "order_items", order_id)
        total = delivered = 0
        with self.db.transaction():
            for item in items:
                extra = qty_to_db(delivered_map.get(item["id"], 0))
                new_total = int(item["delivered_qty"]) + extra
                self.db.update("order_items", item["id"], delivered_qty=new_total)
                total += int(item["quantity"])
                delivered += new_total
            status = ("delivered" if total and delivered >= total
                      else "partial" if delivered else "confirmed")
            self.db.update("orders", order_id, status=status)

    def convert_to_invoice(self, order_id: int, user_id: int | None = None) -> dict:
        source = self.get(order_id)
        if not source:
            return {}
        from .sales import CartItem

        items = items_to_cart(source["items"], CartItem)
        return InvoiceService(self.db, self.numbering, self.stock, self.parties).save(
            items, customer_id=source["party_id"], source_type="order", source_id=order_id,
            notes=source.get("notes", ""), user_id=user_id)


# ---------------------------------------------------------------------------
# Bons de livraison
# ---------------------------------------------------------------------------
class DeliveryService(BaseDocumentService):
    header_table = "delivery_notes"
    items_table = "delivery_items"
    doc_type = "bl"
    party_column = "customer_id"

    def save(self, items: list[dict], *, customer_id: int, date: str = "",
             delivery_address: str = "", source_type: str = "", source_id: int | None = None,
             notes: str = "", route_note_id: int | None = None,
             user_id: int | None = None) -> dict:
        stamp = date or now_iso()
        with self.db.transaction():
            delivery_id = self.db.insert(
                "delivery_notes", number=self.numbering.next_number("bl", stamp), date=stamp,
                customer_id=customer_id, delivery_address=delivery_address,
                source_type=source_type, source_id=source_id, route_note_id=route_note_id,
                notes=notes, created_by=user_id, status="draft")
            for index, item in enumerate(items):
                ordered = qty_to_db(item.get("ordered_qty", item.get("quantity", 0)))
                delivered = qty_to_db(item.get("delivered_qty", item.get("quantity", 0)))
                self.db.insert(
                    "delivery_items", delivery_id=delivery_id, ref_type="product",
                    product_id=item.get("product_id"), code=item.get("code", ""),
                    label=item.get("label", ""), unit=item.get("unit", "u"),
                    ordered_qty=ordered, delivered_qty=delivered,
                    remaining_qty=max(0, ordered - delivered), sort_order=index)
        return self.get(delivery_id)

    def get(self, doc_id: int) -> dict:
        header = self.db.fetch("delivery_notes", doc_id)
        if not header:
            return {}
        header["party"] = self.db.fetch("customers", header["customer_id"]) or {}
        header["items"] = lines_of(self.db, "delivery_items", doc_id)
        header["totals"] = {
            "ordered": db_to_qty(sum(i["ordered_qty"] for i in header["items"])),
            "delivered": db_to_qty(sum(i["delivered_qty"] for i in header["items"])),
            "remaining": db_to_qty(sum(i["remaining_qty"] for i in header["items"])),
        }
        return header

    def set_delivered(self, item_id: int, delivered_qty) -> None:
        item = self.db.fetch("delivery_items", item_id)
        if not item:
            return
        delivered = qty_to_db(delivered_qty)
        self.db.update("delivery_items", item_id, delivered_qty=delivered,
                       remaining_qty=max(0, int(item["ordered_qty"]) - delivered))
        self.refresh_status(item["delivery_id"])

    def refresh_status(self, delivery_id: int) -> str:
        items = lines_of(self.db, "delivery_items", delivery_id)
        ordered = sum(int(i["ordered_qty"]) for i in items)
        delivered = sum(int(i["delivered_qty"]) for i in items)
        status = ("delivered" if ordered and delivered >= ordered
                  else "partial" if delivered else "draft")
        self.db.update("delivery_notes", delivery_id, status=status)
        return status

    def convert_to_invoice(self, delivery_id: int, user_id: int | None = None) -> dict:
        delivery = self.get(delivery_id)
        if not delivery:
            return {}
        items = []
        for row in delivery["items"]:
            if row["delivered_qty"] <= 0:
                continue
            product = self.db.fetch("products", row["product_id"]) or {}
            items.append({
                "ref_type": "product", "ref_id": row["product_id"], "code": row["code"],
                "label": row["label"], "unit": row["unit"],
                "qty": db_to_qty(row["delivered_qty"]),
                "unit_price_cents": int(product.get("sale_price_cents", 0)),
                "vat_rate_bp": int(product.get("vat_rate_bp", 2000)),
                "discount_percent_bp": 0, "discount_cents": 0,
                "cost_cents": int(product.get("purchase_price_cents", 0)),
                "track_stock": False,   # stock already left on the POS sale / BL
            })
        from .sales import CartItem

        cart = [CartItem(**item) for item in items]
        return InvoiceService(self.db, self.numbering, self.stock, self.parties).save(
            cart, customer_id=delivery["customer_id"], source_type="delivery",
            source_id=delivery_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Bons de route
# ---------------------------------------------------------------------------
class RouteNoteService(BaseDocumentService):
    header_table = "route_notes"
    items_table = "route_note_items"
    doc_type = "br"
    party_column = "customer_id"

    def save(self, *, customer_id: int, driver_id: int | None, vehicle_id: int | None,
             date: str = "", delivery_address: str = "", delivery_reference: str = "",
             departure: str = "", destination: str = "", km: int = 0,
             departure_time: str = "", return_time: str = "", notes: str = "",
             items: list[dict] | None = None, user_id: int | None = None,
             route_note_id: int | None = None) -> dict:
        stamp = date or now_iso()
        values = dict(
            date=stamp, customer_id=customer_id, driver_id=driver_id, vehicle_id=vehicle_id,
            delivery_address=delivery_address, delivery_reference=delivery_reference,
            departure=departure, destination=destination, km=int(km or 0),
            departure_time=departure_time, return_time=return_time, notes=notes)
        with self.db.transaction():
            if route_note_id:
                self.db.update("route_notes", route_note_id, **values)
                self.db.execute("DELETE FROM route_note_items WHERE route_note_id = ?",
                                (route_note_id,))
            else:
                route_note_id = self.db.insert(
                    "route_notes", number=self.numbering.next_number("br", stamp),
                    created_by=user_id, status="draft", **values)
            for item in items or []:
                self.db.insert("route_note_items", route_note_id=route_note_id,
                               product_id=item.get("product_id"), label=item.get("label", ""),
                               quantity=qty_to_db(item.get("quantity", 0)),
                               delivery_note_id=item.get("delivery_note_id"))
        return self.get(route_note_id)

    def get(self, doc_id: int) -> dict:
        header = self.db.fetch("route_notes", doc_id)
        if not header:
            return {}
        header["party"] = self.db.fetch("customers", header["customer_id"]) or {}
        header["driver"] = self.db.fetch("drivers", header["driver_id"]) if header.get("driver_id") else {}
        header["vehicle"] = self.db.fetch("vehicles", header["vehicle_id"]) if header.get("vehicle_id") else {}
        header["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM route_note_items WHERE route_note_id = ? ORDER BY id", (doc_id,))]
        return header


# ---------------------------------------------------------------------------
# Factures / avoirs
# ---------------------------------------------------------------------------
class InvoiceService(BaseDocumentService):
    header_table = "invoices"
    items_table = "invoice_items"
    doc_type = "invoice"
    party_column = "customer_id"

    def save(self, items, *, customer_id: int, date: str = "", due_date: str = "",
             invoice_type: str = "standard", source_type: str = "", source_id: int | None = None,
             notes: str = "", terms: str = "", paid_cents: int = 0,
             user_id: int | None = None, invoice_id: int | None = None) -> dict:
        from .sales import cart_totals

        stamp = date or now_iso()
        totals = cart_totals(items)
        total = totals["total_ttc_cents"]
        if not due_date and invoice_type == "credit":
            due_date = (datetime.fromisoformat(stamp.replace(" ", "T")) +
                        timedelta(days=30)).date().isoformat()
        status = ("paid" if paid_cents >= total and total > 0
                  else "partial" if paid_cents > 0 else "unpaid")
        doc_type = "invoice_proforma" if invoice_type == "proforma" else "invoice"

        with self.db.transaction():
            if invoice_id:
                previous = self.db.fetch("invoices", invoice_id)
                self.db.update(
                    "invoices", invoice_id, date=stamp, due_date=due_date,
                    customer_id=customer_id, invoice_type=invoice_type,
                    subtotal_cents=totals["subtotal_ht_cents"],
                    discount_cents=totals["discount_cents"],
                    total_ht_cents=totals["total_ht_cents"],
                    total_vat_cents=totals["total_vat_cents"], total_cents=total,
                    notes=notes, terms=terms, status=status)
                if previous and previous["customer_id"] != customer_id:
                    self.parties.recompute_customer(previous["customer_id"])
                self.db.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            else:
                invoice_id = self.db.insert(
                    "invoices", number=self.numbering.next_number(doc_type, stamp), date=stamp,
                    due_date=due_date, customer_id=customer_id, invoice_type=invoice_type,
                    source_type=source_type, source_id=source_id,
                    subtotal_cents=totals["subtotal_ht_cents"],
                    discount_cents=totals["discount_cents"],
                    total_ht_cents=totals["total_ht_cents"],
                    total_vat_cents=totals["total_vat_cents"], total_cents=total,
                    paid_cents=paid_cents, notes=notes, terms=terms,
                    created_by=user_id, status=status)
            write_lines(self.db, "invoice_items", invoice_id, items, totals)
            self.parties.recompute_customer(customer_id)
        return self.get(invoice_id)

    def record_payment(self, invoice_id: int, amount_cents: int, method: str = "cash",
                       reference: str = "", user_id: int | None = None,
                       cash_session_id: int | None = None, date: str = "") -> dict:
        stamp = date or now_iso()
        invoice = self.db.fetch("invoices", invoice_id)
        if not invoice:
            raise ValueError("facture introuvable")
        with self.db.transaction():
            payment_id = self.db.insert(
                "payments", number=self.numbering.next_number("payment_in", stamp), date=stamp,
                direction="in", party_type="customer", party_id=invoice["customer_id"],
                method=method, amount_cents=int(amount_cents), reference=reference,
                cash_session_id=cash_session_id, created_by=user_id, status="validated")
            self.db.insert("payment_allocations", payment_id=payment_id,
                           invoice_id=invoice_id, amount_cents=int(amount_cents))
            paid = int(invoice["paid_cents"]) + int(amount_cents)
            total = int(invoice["total_cents"])
            status = "paid" if paid >= total else "partial" if paid > 0 else "unpaid"
            self.db.update("invoices", invoice_id, paid_cents=min(paid, total),
                           status=status, payment_method=method)
            self.parties.recompute_customer(invoice["customer_id"])
            if cash_session_id and method == "cash":
                self.db.insert("cash_movements", session_id=cash_session_id, date=stamp,
                               movement_type="payment_in", direction="in",
                               amount_cents=int(amount_cents), method="cash",
                               ref_type="invoice", ref_id=invoice_id,
                               ref_number=invoice["number"], created_by=user_id)
        return self.db.fetch("payments", payment_id)

    def cancel(self, invoice_id: int, user_id: int | None = None) -> None:
        invoice = self.db.fetch("invoices", invoice_id)
        if not invoice:
            return
        self.db.update("invoices", invoice_id, status="cancelled")
        self.parties.recompute_customer(invoice["customer_id"])

    def list_unpaid(self, customer_id: int | None = None) -> list[dict]:
        sql = """SELECT i.*, c.name AS customer_name FROM invoices i
                 LEFT JOIN customers c ON c.id = i.customer_id
                 WHERE i.status IN ('unpaid','partial') AND i.invoice_type <> 'proforma'"""
        params: list = []
        if customer_id:
            sql += " AND i.customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY i.date"
        return [dict(r) for r in self.db.query(sql, params)]

    def create_credit_note(self, *, customer_id: int, items, invoice_id: int | None = None,
                           return_id: int | None = None, reason: str = "",
                           user_id: int | None = None, date: str = "") -> dict:
        from .sales import cart_totals

        stamp = date or now_iso()
        totals = cart_totals(items)
        with self.db.transaction():
            credit_id = self.db.insert(
                "credit_notes", number=self.numbering.next_number("credit_note", stamp),
                date=stamp, customer_id=customer_id, invoice_id=invoice_id,
                return_id=return_id, reason=reason, total_ht_cents=totals["total_ht_cents"],
                total_vat_cents=totals["total_vat_cents"],
                total_cents=totals["total_ttc_cents"], created_by=user_id,
                status="validated")
            for index, item in enumerate(items):
                line = item.to_line()
                net = money_to_cents(line.net_ht)
                vat = int(round(net * int(item.vat_rate_bp) / 10000))
                self.db.insert(
                    "credit_note_items", credit_note_id=credit_id, ref_type=item.ref_type,
                    product_id=item.ref_id if item.ref_type == "product" else None,
                    code=item.code, label=item.label, unit=item.unit,
                    quantity=qty_to_db(item.qty), unit_price_cents=item.unit_price_cents,
                    vat_rate_bp=item.vat_rate_bp, line_ht_cents=net, line_vat_cents=vat,
                    line_total_cents=net + vat)
            self.parties.recompute_customer(customer_id)
        header = self.db.fetch("credit_notes", credit_id)
        header["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM credit_note_items WHERE credit_note_id = ? ORDER BY id", (credit_id,))]
        header["party"] = self.db.fetch("customers", customer_id) or {}
        header["totals"] = {"total_ht": cents_to_money(header["total_ht_cents"]),
                            "total_vat": cents_to_money(header["total_vat_cents"]),
                            "total_ttc": cents_to_money(header["total_cents"])}
        return header


class CreditNoteService:
    """Lecture des avoirs (créés via :meth:`InvoiceService.create_credit_note`)."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, credit_id: int) -> dict:
        header = self.db.fetch("credit_notes", credit_id)
        if not header:
            return {}
        header["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM credit_note_items WHERE credit_note_id = ? ORDER BY id",
            (credit_id,))]
        header["party"] = self.db.fetch("customers", header["customer_id"]) or {}
        header["totals"] = {
            "subtotal_ht": cents_to_money(header.get("total_ht_cents", 0)),
            "total_ht": cents_to_money(header.get("total_ht_cents", 0)),
            "total_vat": cents_to_money(header.get("total_vat_cents", 0)),
            "total_ttc": cents_to_money(header.get("total_cents", 0)),
        }
        return header

    def list(self, term: str = "", status: str = "", date_from: str = "",
             date_to: str = "", limit: int = 500) -> list[dict]:
        where = ["1=1"]
        params: list = []
        if term:
            where.append("cn.number LIKE ?")
            params.append(f"%{term}%")
        if status:
            where.append("cn.status = ?")
            params.append(status)
        if date_from:
            where.append("cn.date >= ?")
            params.append(date_from)
        if date_to:
            where.append("cn.date <= ?")
            params.append(date_to + " 23:59:59")
        return [dict(r) for r in self.db.query(
            "SELECT cn.*, c.name AS customer_name FROM credit_notes cn "
            "LEFT JOIN customers c ON c.id = cn.customer_id WHERE "
            + " AND ".join(where) + " ORDER BY cn.id DESC LIMIT ?",
            (*params, int(limit)))]


# ---------------------------------------------------------------------------
# Bons de retour fournisseur
# ---------------------------------------------------------------------------
class SupplierReturnService:
    def __init__(self, db: Database, numbering: Numbering, stock: StockService):
        self.db = db
        self.numbering = numbering
        self.stock = stock

    def save(self, items: list[dict], *, supplier_id: int, source_type: str = "purchase",
             source_id: int | None = None, source_number: str = "", reason: str = "",
             condition_code: str = "good", date: str = "", user_id: int | None = None,
             validate: bool = True) -> dict:
        stamp = date or now_iso()
        with self.db.transaction():
            return_id = self.db.insert(
                "return_notes", number=self.numbering.next_number("return_supplier", stamp),
                date=stamp, direction="supplier", party_id=supplier_id,
                source_type=source_type, source_id=source_id, source_number=source_number,
                reason=reason, condition_code=condition_code, created_by=user_id,
                status="draft")
            total = 0
            for item in items:
                quantity = qty_to_db(item.get("quantity", 0))
                if quantity <= 0:
                    continue
                unit_price = int(item.get("unit_price_cents", 0))
                line_total = int(round(quantity / 1000 * unit_price))
                self.db.insert(
                    "return_items", return_id=return_id, ref_type="product",
                    product_id=item.get("product_id"), code=item.get("code", ""),
                    label=item.get("label", ""), unit=item.get("unit", "u"),
                    quantity=quantity, unit_price_cents=unit_price,
                    vat_rate_bp=int(item.get("vat_rate_bp", 0)), line_total_cents=line_total,
                    reason=item.get("reason", reason), condition_code=condition_code, restock=0)
                total += line_total
                if validate:
                    self.stock.move(item["product_id"], -db_to_qty(quantity),
                                    "return_supplier", ref_type="return_supplier",
                                    ref_id=return_id, reason=reason, user_id=user_id)
            self.db.update("return_notes", return_id, refund_cents=total,
                           status="validated" if validate else "draft")
        return self.db.fetch("return_notes", return_id)

    def get(self, return_id: int) -> dict:
        header = self.db.fetch("return_notes", return_id)
        if not header:
            return {}
        header["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM return_items WHERE return_id = ? ORDER BY id", (return_id,))]
        header["party"] = (self.db.fetch("suppliers" if header["direction"] == "supplier"
                                         else "customers", header["party_id"]) or {})
        return header


# ---------------------------------------------------------------------------
# Achats
# ---------------------------------------------------------------------------
class PurchaseService:
    def __init__(self, db: Database, numbering: Numbering, stock: StockService,
                 parties: PartyService):
        self.db = db
        self.numbering = numbering
        self.stock = stock
        self.parties = parties

    def save(self, items, *, supplier_id: int, date: str = "", supplier_ref: str = "",
             expected_date: str = "", notes: str = "", user_id: int | None = None,
             purchase_id: int | None = None) -> dict:
        from .sales import cart_totals

        stamp = date or now_iso()
        totals = cart_totals(items)
        with self.db.transaction():
            if purchase_id:
                self.db.update("purchases", purchase_id, date=stamp, supplier_id=supplier_id,
                               supplier_ref=supplier_ref, expected_date=expected_date,
                               subtotal_cents=totals["subtotal_ht_cents"],
                               discount_cents=totals["discount_cents"],
                               total_ht_cents=totals["total_ht_cents"],
                               total_vat_cents=totals["total_vat_cents"],
                               total_cents=totals["total_ttc_cents"], notes=notes)
                self.db.execute("DELETE FROM purchase_items WHERE purchase_id = ?",
                                (purchase_id,))
            else:
                purchase_id = self.db.insert(
                    "purchases", number=self.numbering.next_number("purchase", stamp),
                    date=stamp, supplier_id=supplier_id, supplier_ref=supplier_ref,
                    expected_date=expected_date, subtotal_cents=totals["subtotal_ht_cents"],
                    discount_cents=totals["discount_cents"],
                    total_ht_cents=totals["total_ht_cents"],
                    total_vat_cents=totals["total_vat_cents"],
                    total_cents=totals["total_ttc_cents"], notes=notes,
                    created_by=user_id, status="ordered")
            write_lines(self.db, "purchase_items", purchase_id, items, totals)
        return self.get(purchase_id)

    def get(self, purchase_id: int) -> dict:
        header = self.db.fetch("purchases", purchase_id)
        if not header:
            return {}
        header["party"] = self.db.fetch("suppliers", header["supplier_id"]) or {}
        return document_view(self.db, header, "purchase_items")

    def list(self, term: str = "", status: str = "", limit: int = 500) -> list[dict]:
        sql = """SELECT p.*, s.name AS supplier_name FROM purchases p
                 LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE 1=1"""
        params: list = []
        if term:
            sql += " AND (p.number LIKE ? OR s.name LIKE ?)"
            params += [f"%{term}%", f"%{term}%"]
        if status:
            sql += " AND p.status = ?"
            params.append(status)
        sql += " ORDER BY p.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    # -- workflow -----------------------------------------------------------
    def receive(self, purchase_id: int, received: dict[int, Any], *, user_id: int | None = None,
                date: str = "", update_cost: bool = True) -> dict:
        """Goods received: stock goes up, received quantities are tracked."""
        purchase = self.get(purchase_id)
        if not purchase:
            raise ValueError("commande fournisseur introuvable")
        stamp = date or now_iso()
        receipt_lines = []
        with self.db.transaction():
            receipt_id = self.db.insert(
                "purchase_receipts", number=self.numbering.next_number("purchase_receipt", stamp),
                date=stamp, purchase_id=purchase_id, supplier_id=purchase["supplier_id"],
                created_by=user_id, status="validated")
            for item in purchase["items"]:
                quantity = qty_to_db(received.get(item["id"], 0))
                if quantity <= 0:
                    continue
                new_received = int(item["received_qty"]) + quantity
                self.db.update("purchase_items", item["id"], received_qty=new_received)
                self.db.insert("purchase_receipt_items", receipt_id=receipt_id,
                               product_id=item["product_id"], quantity=quantity,
                               unit_price_cents=item["unit_price_cents"])
                receipt_lines.append((item, quantity))
                if item["product_id"]:
                    self.stock.move(item["product_id"], db_to_qty(quantity), "purchase",
                                    ref_type="purchase_receipt", ref_id=receipt_id,
                                    ref_number=purchase["number"],
                                    unit_cost_cents=item["unit_price_cents"],
                                    reason="R\u00e9ception commande fournisseur",
                                    user_id=user_id, timestamp=stamp)
                    if update_cost:
                        self.db.execute(
                            "UPDATE products SET purchase_price_cents = ?, updated_at = ? "
                            "WHERE id = ?", (item["unit_price_cents"], now_iso(),
                                             item["product_id"]))

            total_ordered = sum(int(i["quantity"]) for i in purchase["items"])
            total_received = sum(int(i["received_qty"]) for i in purchase["items"]) + \
                sum(q for _, q in receipt_lines)
            status = ("received" if total_ordered and total_received >= total_ordered
                      else "partial" if total_received else "ordered")
            self.db.update("purchases", purchase_id, status=status)
        return self.db.fetch("purchase_receipts", receipt_id)

    def create_supplier_invoice(self, purchase_id: int, *, total_ht_cents: int | None = None,
                                vat_cents: int | None = None, supplier_invoice_ref: str = "",
                                date: str = "", due_date: str = "",
                                user_id: int | None = None) -> dict:
        purchase = self.get(purchase_id)
        if not purchase:
            raise ValueError("commande fournisseur introuvable")
        stamp = date or now_iso()
        ht = int(total_ht_cents if total_ht_cents is not None else purchase["total_ht_cents"])
        vat = int(vat_cents if vat_cents is not None else purchase["total_vat_cents"])
        with self.db.transaction():
            invoice_id = self.db.insert(
                "purchase_invoices", number=self.numbering.next_number("purchase_invoice", stamp),
                date=stamp, due_date=due_date, supplier_id=purchase["supplier_id"],
                purchase_id=purchase_id, supplier_invoice_ref=supplier_invoice_ref,
                total_ht_cents=ht, total_vat_cents=vat, total_cents=ht + vat, paid_cents=0,
                created_by=user_id, status="unpaid")
            self.db.update("purchases", purchase_id, status="invoiced")
            self.parties.recompute_supplier(purchase["supplier_id"])
        return self.db.fetch("purchase_invoices", invoice_id)

    def pay_supplier_invoice(self, invoice_id: int, amount_cents: int, method: str = "transfer",
                             reference: str = "", user_id: int | None = None,
                             date: str = "", cash_session_id: int | None = None) -> dict:
        stamp = date or now_iso()
        invoice = self.db.fetch("purchase_invoices", invoice_id)
        if not invoice:
            raise ValueError("facture fournisseur introuvable")
        with self.db.transaction():
            payment_id = self.db.insert(
                "payments", number=self.numbering.next_number("payment_out", stamp), date=stamp,
                direction="out", party_type="supplier", party_id=invoice["supplier_id"],
                method=method, amount_cents=int(amount_cents), reference=reference,
                cash_session_id=cash_session_id, created_by=user_id, status="validated")
            self.db.insert("payment_allocations", payment_id=payment_id,
                           purchase_invoice_id=invoice_id, amount_cents=int(amount_cents))
            paid = int(invoice["paid_cents"]) + int(amount_cents)
            total = int(invoice["total_cents"])
            status = "paid" if paid >= total else "partial" if paid > 0 else "unpaid"
            self.db.update("purchase_invoices", invoice_id, paid_cents=min(paid, total),
                           status=status)
            self.parties.recompute_supplier(invoice["supplier_id"])
            if cash_session_id and method == "cash":
                self.db.insert("cash_movements", session_id=cash_session_id, date=stamp,
                               movement_type="payment_out", direction="out",
                               amount_cents=int(amount_cents), method="cash",
                               ref_type="purchase_invoice", ref_id=invoice_id,
                               ref_number=invoice["number"], created_by=user_id)
        return self.db.fetch("payments", payment_id)

    def supplier_invoices(self, supplier_id: int | None = None,
                          status: str = "") -> list[dict]:
        sql = """SELECT pi.*, s.name AS supplier_name FROM purchase_invoices pi
                 LEFT JOIN suppliers s ON s.id = pi.supplier_id WHERE 1=1"""
        params: list = []
        if supplier_id:
            sql += " AND pi.supplier_id = ?"
            params.append(supplier_id)
        if status:
            sql += " AND pi.status = ?"
            params.append(status)
        sql += " ORDER BY pi.id DESC"
        return [dict(r) for r in self.db.query(sql, params)]

    def history(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self.db.query(
            """SELECT p.date, pi.quantity, pi.label, pi.unit_price_cents,
                      pi.line_total_cents, p.number AS purchase_number, s.name AS supplier_name
               FROM purchase_items pi
               JOIN purchases p ON p.id = pi.purchase_id
               LEFT JOIN suppliers s ON s.id = p.supplier_id
               ORDER BY pi.id DESC LIMIT ?""", (int(limit),))]


# ---------------------------------------------------------------------------
# D\u00e9penses
# ---------------------------------------------------------------------------
class ExpenseService:
    def __init__(self, db: Database, numbering: Numbering):
        self.db = db
        self.numbering = numbering

    def save(self, *, date: str = "", category_id: int | None, description: str,
             amount_cents: int, method: str = "cash", supplier_id: int | None = None,
             attachment_path: str = "", notes: str = "", cash_session_id: int | None = None,
             user_id: int | None = None, expense_id: int | None = None) -> dict:
        stamp = date or now_iso()
        values = dict(date=stamp, category_id=category_id, description=description,
                      amount_cents=int(amount_cents), method=method, supplier_id=supplier_id,
                      attachment_path=attachment_path, cash_session_id=cash_session_id,
                      notes=notes)
        with self.db.transaction():
            if expense_id:
                self.db.update("expenses", expense_id, **values)
            else:
                expense_id = self.db.insert(
                    "expenses", number=self.numbering.next_number("expense", stamp),
                    created_by=user_id, status="validated", **values)
            if cash_session_id and method == "cash":
                self.db.execute("DELETE FROM cash_movements WHERE ref_type='expense' AND ref_id=?",
                                (expense_id,))
                self.db.insert("cash_movements", session_id=cash_session_id, date=stamp,
                               movement_type="expense", direction="out",
                               amount_cents=int(amount_cents), method="cash",
                               ref_type="expense", ref_id=expense_id,
                               ref_number=f"DEP-{expense_id}", created_by=user_id)
        return self.db.fetch("expenses", expense_id)

    def list(self, date_from: str = "", date_to: str = "", category_id: int | None = None,
             limit: int = 500) -> list[dict]:
        sql = """SELECT e.*, c.name AS category_name, s.name AS supplier_name
                 FROM expenses e LEFT JOIN categories c ON c.id = e.category_id
                 LEFT JOIN suppliers s ON s.id = e.supplier_id WHERE 1=1"""
        params: list = []
        if date_from:
            sql += " AND e.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND e.date <= ?"
            params.append(date_to + " 23:59:59")
        if category_id:
            sql += " AND e.category_id = ?"
            params.append(category_id)
        sql += " ORDER BY e.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    def total_for_period(self, date_from: str, date_to: str) -> int:
        return int(self.db.scalar(
            "SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE date >= ? AND date <= ?",
            (date_from, date_to + " 23:59:59"), default=0))

    def by_category(self, date_from: str, date_to: str) -> list[dict]:
        rows = self.db.query(
            """SELECT COALESCE(c.name,'Autres') AS category,
                      COALESCE(SUM(e.amount_cents),0) AS total
               FROM expenses e LEFT JOIN categories c ON c.id = e.category_id
               WHERE e.date >= ? AND e.date <= ? GROUP BY c.name ORDER BY total DESC""",
            (date_from, date_to + " 23:59:59"))
        return [{"category": r["category"], "total_cents": r["total"],
                 "total": cents_to_money(r["total"])} for r in rows]

    def delete(self, expense_id: int) -> None:
        self.db.execute("DELETE FROM cash_movements WHERE ref_type='expense' AND ref_id=?",
                        (expense_id,))
        self.db.delete("expenses", expense_id)


# ---------------------------------------------------------------------------
# Paiements
# ---------------------------------------------------------------------------
class PaymentService:
    def __init__(self, db: Database, numbering: Numbering, parties: PartyService):
        self.db = db
        self.numbering = numbering
        self.parties = parties

    def save(self, *, direction: str, party_type: str, party_id: int, amount_cents: int,
             method: str = "cash", reference: str = "", notes: str = "", date: str = "",
             invoice_ids: list[int] | None = None, cash_session_id: int | None = None,
             user_id: int | None = None) -> dict:
        stamp = date or now_iso()
        doc_type = "payment_in" if direction == "in" else "payment_out"
        with self.db.transaction():
            payment_id = self.db.insert(
                "payments", number=self.numbering.next_number(doc_type, stamp), date=stamp,
                direction=direction, party_type=party_type, party_id=party_id, method=method,
                amount_cents=int(amount_cents), reference=reference, notes=notes,
                cash_session_id=cash_session_id, created_by=user_id, status="validated")
            for invoice_id in invoice_ids or []:
                self.db.insert("payment_allocations", payment_id=payment_id,
                               invoice_id=invoice_id, amount_cents=int(amount_cents))
                invoice = self.db.fetch("invoices", invoice_id)
                if invoice:
                    paid = int(invoice["paid_cents"]) + int(amount_cents)
                    total = int(invoice["total_cents"])
                    self.db.update("invoices", invoice_id, paid_cents=min(paid, total),
                                   status="paid" if paid >= total else "partial",
                                   payment_method=method)
            if party_type == "customer":
                self.parties.recompute_customer(party_id)
            else:
                self.parties.recompute_supplier(party_id)
            if cash_session_id and method == "cash":
                self.db.insert("cash_movements", session_id=cash_session_id, date=stamp,
                               movement_type="payment_in" if direction == "in" else "payment_out",
                               direction=direction, amount_cents=int(amount_cents),
                               method="cash", ref_type="payment", ref_id=payment_id,
                               created_by=user_id)
        return self.get(payment_id)

    def get(self, payment_id: int) -> dict:
        header = self.db.fetch("payments", payment_id)
        if not header:
            return {}
        table = "customers" if header["party_type"] == "customer" else "suppliers"
        header["party"] = self.db.fetch(table, header["party_id"]) or {}
        header["allocations"] = [dict(r) for r in self.db.query(
            "SELECT * FROM payment_allocations WHERE payment_id = ?", (payment_id,))]
        return header

    def list(self, direction: str = "", date_from: str = "", date_to: str = "",
             limit: int = 500) -> list[dict]:
        sql = """SELECT p.*, c.name AS customer_name, s.name AS supplier_name
                 FROM payments p
                 LEFT JOIN customers c ON c.id = p.party_id AND p.party_type='customer'
                 LEFT JOIN suppliers s ON s.id = p.party_id AND p.party_type='supplier'
                 WHERE 1=1"""
        params: list = []
        if direction:
            sql += " AND p.direction = ?"
            params.append(direction)
        if date_from:
            sql += " AND p.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND p.date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " ORDER BY p.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    def delete(self, payment_id: int) -> None:
        payment = self.db.fetch("payments", payment_id)
        if not payment:
            return
        for allocation in self.db.query(
                "SELECT * FROM payment_allocations WHERE payment_id = ?", (payment_id,)):
            if allocation["invoice_id"]:
                invoice = self.db.fetch("invoices", allocation["invoice_id"])
                if invoice:
                    paid = max(0, int(invoice["paid_cents"]) - int(allocation["amount_cents"]))
                    total = int(invoice["total_cents"])
                    self.db.update("invoices", invoice["id"], paid_cents=paid,
                                   status="paid" if paid >= total else
                                   "partial" if paid else "unpaid")
        self.db.execute("DELETE FROM cash_movements WHERE ref_type='payment' AND ref_id=?",
                        (payment_id,))
        self.db.execute("DELETE FROM payment_allocations WHERE payment_id=?", (payment_id,))
        self.db.delete("payments", payment_id)
        if payment["party_type"] == "customer":
            self.parties.recompute_customer(payment["party_id"])
        else:
            self.parties.recompute_supplier(payment["party_id"])


# ---------------------------------------------------------------------------
# Caisse
# ---------------------------------------------------------------------------
class CashService:
    def __init__(self, db: Database, numbering: Numbering):
        self.db = db
        self.numbering = numbering

    def open_session(self, opening_cents: int, user_id: int | None = None,
                     notes: str = "") -> dict:
        existing = self.current_session()
        if existing:
            raise ValueError("Une session de caisse est d\u00e9j\u00e0 ouverte")
        number = self.numbering.next_number("cash_session")
        session_id = self.db.insert(
            "cash_sessions", number=number, opened_at=now_iso(),
            opening_cents=int(opening_cents), user_id=user_id, notes=notes,
            created_by=user_id, status="open")
        self.db.insert("cash_movements", session_id=session_id, date=now_iso(),
                       movement_type="open", direction="in", amount_cents=int(opening_cents),
                       method="cash", created_by=user_id)
        return self.db.fetch("cash_sessions", session_id)

    def close_session(self, counted_cents: int, user_id: int | None = None,
                      notes: str = "") -> dict:
        session = self.current_session()
        if not session:
            raise ValueError("Aucune session de caisse ouverte")
        summary = self.summary(session["id"])
        difference = int(counted_cents) - summary["theoretical_cents"]
        with self.db.transaction():
            self.db.insert("cash_movements", session_id=session["id"], date=now_iso(),
                           movement_type="close", direction="out" if difference > 0 else "in",
                           amount_cents=abs(int(counted_cents)), method="cash",
                           notes=notes, created_by=user_id)
            self.db.update("cash_sessions", session["id"], closed_at=now_iso(),
                           closing_cents=summary["theoretical_cents"],
                           counted_cents=int(counted_cents), difference_cents=difference,
                           status="closed", notes=notes)
        return self.summary(session["id"])

    def current_session(self) -> dict:
        row = self.db.query_one("SELECT * FROM cash_sessions WHERE status='open' "
                                "ORDER BY id DESC LIMIT 1")
        return dict(row) if row else {}

    def sessions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.query(
            """SELECT cs.*, u.username FROM cash_sessions cs
               LEFT JOIN users u ON u.id = cs.user_id ORDER BY cs.id DESC LIMIT ?""",
            (int(limit),))]

    def summary(self, session_id: int) -> dict:
        session = self.db.fetch("cash_sessions", session_id)
        if not session:
            return {}
        rows = self.db.query(
            """SELECT movement_type, COALESCE(SUM(amount_cents),0) AS total
               FROM cash_movements WHERE session_id = ? GROUP BY movement_type""",
            (session_id,))
        per_type = {r["movement_type"]: int(r["total"]) for r in rows}
        opening = int(session["opening_cents"])
        sales = per_type.get("sale", 0)
        payments_in = per_type.get("payment_in", 0)
        expenses = per_type.get("expense", 0)
        payments_out = per_type.get("payment_out", 0)
        refunds = per_type.get("refund", 0)
        deposits = per_type.get("deposit", 0)
        withdrawals = per_type.get("withdrawal", 0)
        theoretical = (opening + sales + payments_in + deposits
                       - expenses - payments_out - withdrawals - refunds)
        sales_count = int(self.db.scalar(
            "SELECT COUNT(*) FROM sales WHERE cash_session_id = ? AND status='validated'",
            (session_id,), default=0))
        return {
            "session": session,
            "opening_cents": opening,
            "sales_cents": sales,
            "payments_in_cents": payments_in,
            "expenses_cents": expenses,
            "payments_out_cents": payments_out,
            "refunds_cents": refunds,
            "deposits_cents": deposits,
            "withdrawals_cents": withdrawals,
            "theoretical_cents": theoretical,
            "counted_cents": int(session["counted_cents"] or 0),
            "difference_cents": int(session["difference_cents"] or 0),
            "sales_count": sales_count,
            "by_method": self.by_method(session_id),
            "theoretical_money": cents_to_money(theoretical),
        }

    def by_method(self, session_id: int) -> list[dict]:
        rows = self.db.query(
            """SELECT COALESCE(sp.method, s.payment_method) AS method,
                      COUNT(DISTINCT s.id) AS count,
                      COALESCE(SUM(sp.amount_cents),0) AS total
               FROM sales s LEFT JOIN sale_payments sp ON sp.sale_id = s.id
               WHERE s.cash_session_id = ? AND s.status='validated'
               GROUP BY method""", (session_id,))
        return [{"method": r["method"], "count": r["count"],
                 "total": cents_to_money(r["total"])} for r in rows]

    def add_movement(self, movement_type: str, amount_cents: int, notes: str = "",
                     user_id: int | None = None, session_id: int | None = None) -> int:
        """Record a manual drawer movement (deposit / withdrawal)."""
        if movement_type not in ("deposit", "withdrawal"):
            raise ValueError("type de mouvement invalide")
        session = self.db.fetch("cash_sessions", session_id) if session_id \
            else self.current_session()
        if not session:
            raise ValueError("Aucune session de caisse ouverte")
        return self.db.insert("cash_movements", session_id=session["id"], date=now_iso(),
                              movement_type=movement_type,
                              direction="in" if movement_type == "deposit" else "out",
                              amount_cents=int(amount_cents), method="cash",
                              notes=notes, created_by=user_id)

    def movements(self, session_id: int | None = None) -> list[dict]:
        if session_id is None:
            session = self.current_session()
            session_id = session.get("id") if session else None
            if session_id is None:
                return []
        return [dict(r) for r in self.db.query(
            "SELECT * FROM cash_movements WHERE session_id = ? ORDER BY id", (session_id,))]

    def daily_report(self, day: str) -> dict:
        day_from = f"{day} 00:00:00"
        day_to = f"{day} 23:59:59"
        sales = self.db.query_one(
            """SELECT COUNT(*) AS count, COALESCE(SUM(total_cents),0) AS total,
                      COALESCE(SUM(total_ht_cents),0) AS total_ht,
                      COALESCE(SUM(total_vat_cents),0) AS vat,
                      COALESCE(SUM(cost_cents),0) AS cost
               FROM sales WHERE status='validated' AND date BETWEEN ? AND ?""",
            (day_from, day_to))
        expenses = int(self.db.scalar(
            "SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE date BETWEEN ? AND ?",
            (day_from, day_to), default=0))
        payments_in = int(self.db.scalar(
            """SELECT COALESCE(SUM(amount_cents),0) FROM payments
               WHERE direction='in' AND date BETWEEN ? AND ?""", (day_from, day_to), default=0))
        payments_out = int(self.db.scalar(
            """SELECT COALESCE(SUM(amount_cents),0) FROM payments
               WHERE direction='out' AND date BETWEEN ? AND ?""", (day_from, day_to), default=0))
        data = dict(sales) if sales else {}
        data.update({
            "day": day, "expenses_cents": expenses,
            "payments_in_cents": payments_in, "payments_out_cents": payments_out,
            "net_cash_cents": int(data.get("total", 0)) + payments_in - payments_out - expenses,
        })
        for key in ("total", "total_ht", "vat", "cost", "expenses_cents",
                    "payments_in_cents", "payments_out_cents", "net_cash_cents"):
            data[f"{key}_money"] = cents_to_money(data.get(key, 0))
        data["profit_money"] = cents_to_money(int(data.get("total_ht", 0))
                                              - int(data.get("cost", 0)))
        return data


# ---------------------------------------------------------------------------
# R\u00e9parations
# ---------------------------------------------------------------------------
class RepairService:
    def __init__(self, db: Database, numbering: Numbering, stock: StockService):
        self.db = db
        self.numbering = numbering
        self.stock = stock

    def save(self, *, customer_id: int, device_type: str, device_brand: str = "",
             device_model: str = "", serial_number: str = "", accessories: str = "",
             problem: str = "", diagnosis: str = "", repair_performed: str = "",
             labor_cents: int = 0, parts: list[dict] | None = None,
             deposit_cents: int = 0, technician_id: int | None = None, date: str = "",
             eta: str = "", warranty_days: int = 0, notes: str = "",
             status: str = "received", user_id: int | None = None,
             repair_id: int | None = None) -> dict:
        stamp = date or now_iso()
        parts = parts or []
        for part in parts:
            if "line_total_cents" not in part:
                part["line_total_cents"] = int(round(
                    qty_to_db(part.get("quantity", 1)) / 1000
                    * int(part.get("unit_price_cents", 0))))
        parts_cents = sum(int(p.get("line_total_cents", 0)) for p in parts)
        total = int(labor_cents) + parts_cents
        values = dict(date=stamp, customer_id=customer_id, device_type=device_type,
                      device_brand=device_brand, device_model=device_model,
                      serial_number=serial_number, accessories=accessories, problem=problem,
                      diagnosis=diagnosis, repair_performed=repair_performed,
                      labor_cents=int(labor_cents), parts_cents=parts_cents,
                      total_cents=total, deposit_cents=int(deposit_cents),
                      technician_id=technician_id, eta=eta, warranty_days=int(warranty_days),
                      notes=notes, status=status)
        with self.db.transaction():
            if repair_id:
                self.db.update("repairs", repair_id, **values)
                self.db.execute("DELETE FROM repair_items WHERE repair_id = ?", (repair_id,))
            else:
                repair_id = self.db.insert("repairs",
                                           number=self.numbering.next_number("repair", stamp),
                                           created_by=user_id, **values)
            for part in parts:
                quantity = qty_to_db(part.get("quantity", 1))
                unit_price = int(part.get("unit_price_cents", 0))
                line_total = int(part.get("line_total_cents",
                                          round(quantity / 1000 * unit_price)))
                self.db.insert("repair_items", repair_id=repair_id,
                               product_id=part.get("product_id"), code=part.get("code", ""),
                               label=part.get("label", ""), unit=part.get("unit", "u"),
                               quantity=quantity, unit_price_cents=unit_price,
                               line_total_cents=line_total)
                if part.get("product_id") and part.get("consume_stock", True):
                    self.stock.move(part["product_id"], -db_to_qty(quantity), "repair_part",
                                    ref_type="repair", ref_id=repair_id,
                                    reason="Pi\u00e8ce r\u00e9paration", user_id=user_id)
        return self.get(repair_id)

    def get(self, repair_id: int) -> dict:
        header = self.db.fetch("repairs", repair_id)
        if not header:
            return {}
        header["party"] = self.db.fetch("customers", header["customer_id"]) or {}
        header["technician"] = (self.db.fetch("users", header["technician_id"])
                                if header.get("technician_id") else {})
        header["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM repair_items WHERE repair_id = ? ORDER BY id", (repair_id,))]
        header["remaining_cents"] = int(header["total_cents"]) - int(header["deposit_cents"])
        header["remaining_money"] = cents_to_money(header["remaining_cents"])
        header["total_money"] = cents_to_money(header["total_cents"])
        return header

    def list(self, status: str = "", term: str = "", limit: int = 500) -> list[dict]:
        sql = """SELECT r.*, c.name AS customer_name, u.full_name AS technician_name
                 FROM repairs r
                 LEFT JOIN customers c ON c.id = r.customer_id
                 LEFT JOIN users u ON u.id = r.technician_id WHERE 1=1"""
        params: list = []
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        if term:
            like = f"%{term}%"
            sql += " AND (r.number LIKE ? OR c.name LIKE ? OR r.device_model LIKE ? " \
                   "OR r.serial_number LIKE ?)"
            params += [like] * 4
        sql += " ORDER BY r.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    def set_status(self, repair_id: int, status: str, user_id: int | None = None) -> None:
        values: dict = {"status": status}
        if status == "done":
            values["completed_at"] = now_iso()
        if status == "delivered":
            values["delivered_at"] = now_iso()
        self.db.update("repairs", repair_id, **values)

    def invoice_repair(self, repair_id: int, user_id: int | None = None) -> dict:
        """Turn a finished repair into an invoice (labor + parts)."""
        from .sales import CartItem

        repair = self.get(repair_id)
        if not repair:
            raise ValueError("bon de r\u00e9paration introuvable")
        if repair.get("invoice_id"):
            return InvoiceService(self.db, self.numbering, self.stock, None).get(
                repair["invoice_id"])

        items: list[CartItem] = []
        for part in repair["items"]:
            items.append(CartItem(ref_type="product", ref_id=part["product_id"],
                                  code=part["code"], label=part["label"], unit=part["unit"],
                                  qty=db_to_qty(part["quantity"]),
                                  unit_price_cents=part["unit_price_cents"],
                                  vat_rate_bp=2000, track_stock=False))
        if repair["labor_cents"]:
            service = self.db.query_one(
                "SELECT * FROM services WHERE code='SVC-REP-PC' LIMIT 1")
            items.append(CartItem(ref_type="service",
                                  ref_id=service["id"] if service else None,
                                  code="SVC-REP-PC", label="Main d'\u0153uvre r\u00e9paration",
                                  unit="u", qty=1, unit_price_cents=repair["labor_cents"],
                                  vat_rate_bp=2000, track_stock=False))

        invoice = InvoiceService(self.db, self.numbering, self.stock,
                                 PartyService(self.db)).save(
            items, customer_id=repair["customer_id"], invoice_type="standard",
            source_type="repair", source_id=repair_id,
            paid_cents=int(repair["deposit_cents"]), user_id=user_id,
            notes=f"Bon de r\u00e9paration {repair['number']}")
        self.db.update("repairs", repair_id, invoice_id=invoice["id"])
        return invoice

    def activity(self, date_from: str, date_to: str) -> dict:
        rows = self.db.query(
            """SELECT status, COUNT(*) AS count, COALESCE(SUM(total_cents),0) AS total,
                      COALESCE(SUM(deposit_cents),0) AS deposits
               FROM repairs WHERE date >= ? AND date <= ? GROUP BY status""",
            (date_from, date_to + " 23:59:59"))
        return {r["status"]: {"count": r["count"], "total": cents_to_money(r["total"]),
                              "deposits": cents_to_money(r["deposits"])} for r in rows}
