"""Sales / point-of-sale engine.

A validated POS sale produces, atomically:

* one ``sales`` row + ``sale_items`` + ``sale_payments``
* one stock movement per stockable line (or a restock when returning)
* an ``invoices`` row when the sale is invoiced (always for credit sales)
* a ``cash_movements`` row when cash is handled and a session is open
* the customer balance update for credit sales
* an audit log entry

Returns go through :meth:`SalesService.create_return`, which restocks, issues
a credit note and reverses the customer balance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from ..db.database import Database, now_iso
from .money import (Line, cents_to_money, compute_totals, db_to_qty, money_to_cents,
                    qty_to_db, to_decimal)
from .numbering import Numbering
from .parties import PartyService
from .stock import StockError, StockService


@dataclass
class CartItem:
    """A POS/invoice line before it is persisted."""

    ref_type: str = "product"
    ref_id: int | None = None
    code: str = ""
    label: str = ""
    unit: str = "u"
    qty: Any = 1
    unit_price_cents: int = 0
    vat_rate_bp: int = 2000
    discount_percent_bp: int = 0
    discount_cents: int = 0
    cost_cents: int = 0
    track_stock: bool = True
    extra: dict = field(default_factory=dict)

    def to_line(self) -> Line:
        return Line(
            ref_type=self.ref_type, ref_id=self.ref_id, code=self.code, label=self.label,
            unit=self.unit, qty=to_decimal(self.qty),
            unit_price_ht=cents_to_money(self.unit_price_cents),
            vat_rate=Decimal(self.vat_rate_bp) / Decimal(100),
            discount_percent=Decimal(self.discount_percent_bp) / Decimal(100),
            discount_fixed=cents_to_money(self.discount_cents),
        )

    @classmethod
    def from_product(cls, product: dict, qty: Any = 1) -> "CartItem":
        return cls(ref_type="product", ref_id=product["id"], code=product.get("sku", ""),
                   label=product.get("name", ""), unit=product.get("unit", "u"), qty=qty,
                   unit_price_cents=int(product.get("sale_price_cents", 0)),
                   vat_rate_bp=int(product.get("vat_rate_bp", 2000)),
                   cost_cents=int(product.get("purchase_price_cents", 0)),
                   track_stock=bool(product.get("track_stock", 1)))

    @classmethod
    def from_service(cls, service: dict, qty: Any = 1) -> "CartItem":
        return cls(ref_type="service", ref_id=service["id"], code=service.get("code", ""),
                   label=service.get("name", ""), unit=service.get("unit", "u"), qty=qty,
                   unit_price_cents=int(service.get("price_cents", 0)),
                   vat_rate_bp=int(service.get("vat_rate_bp", 2000)),
                   cost_cents=int(service.get("cost_cents", 0)), track_stock=False)

    def as_dict(self) -> dict:
        return {
            "ref_type": self.ref_type, "ref_id": self.ref_id, "code": self.code,
            "label": self.label, "unit": self.unit, "qty": str(to_decimal(self.qty)),
            "unit_price_cents": self.unit_price_cents, "vat_rate_bp": self.vat_rate_bp,
            "discount_percent_bp": self.discount_percent_bp,
            "discount_cents": self.discount_cents, "cost_cents": self.cost_cents,
            "track_stock": self.track_stock, "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CartItem":
        return cls(ref_type=data.get("ref_type", "product"), ref_id=data.get("ref_id"),
                   code=data.get("code", ""), label=data.get("label", ""),
                   unit=data.get("unit", "u"), qty=data.get("qty", 1),
                   unit_price_cents=int(data.get("unit_price_cents", 0)),
                   vat_rate_bp=int(data.get("vat_rate_bp", 0)),
                   discount_percent_bp=int(data.get("discount_percent_bp", 0)),
                   discount_cents=int(data.get("discount_cents", 0)),
                   cost_cents=int(data.get("cost_cents", 0)),
                   track_stock=bool(data.get("track_stock", True)),
                   extra=data.get("extra", {}))


def cart_lines(items) -> list[Line]:
    return [item.to_line() for item in items]


def cart_totals(items, global_discount_percent=0, global_discount_fixed=0) -> dict:
    return compute_totals(cart_lines(items), to_decimal(global_discount_percent),
                          to_decimal(global_discount_fixed))


class SalesService:
    def __init__(self, db: Database, numbering: Numbering, stock: StockService,
                 parties: PartyService):
        self.db = db
        self.numbering = numbering
        self.stock = stock
        self.parties = parties

    # ------------------------------------------------------------------
    # product / service lookup used by the POS search box and the scanner
    # ------------------------------------------------------------------
    def find_by_code(self, code: str) -> CartItem | None:
        code = (code or "").strip()
        if not code:
            return None
        product = self.db.query_one(
            "SELECT * FROM products WHERE (sku = ? OR barcode = ?) AND is_active = 1",
            (code, code))
        if product:
            return CartItem.from_product(dict(product))
        service = self.db.query_one("SELECT * FROM services WHERE code = ? AND is_active = 1",
                                    (code,))
        if service:
            return CartItem.from_service(dict(service))
        return None

    def search(self, term: str, limit: int = 40, include_services: bool = True) -> list[dict]:
        term = (term or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        rows = [dict(r) for r in self.db.query(
            """SELECT id, sku AS code, name, 'product' AS kind, sale_price_cents AS price_cents,
                      vat_rate_bp, stock, unit, purchase_price_cents AS cost_cents,
                      track_stock
               FROM products
               WHERE is_active = 1 AND sellable = 1
                 AND (name LIKE ? OR sku LIKE ? OR barcode = ? OR reference LIKE ?)
               ORDER BY name LIMIT ?""", (like, like, term, like, limit))]
        if include_services:
            rows += [dict(r) for r in self.db.query(
                """SELECT id, code, name, 'service' AS kind, price_cents, vat_rate_bp,
                          0 AS stock, unit, cost_cents, 0 AS track_stock
                   FROM services WHERE is_active = 1 AND (name LIKE ? OR code LIKE ?)
                   ORDER BY name LIMIT ?""", (like, like, limit))]
        return rows

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    def validate_sale(self, items, *, customer_id: int | None = None,
                      payment_method: str = "cash", payments: list[dict] | None = None,
                      amount_received_cents: int = 0, discount_percent_bp: int = 0,
                      discount_cents: int = 0, notes: str = "", cash_session_id: int | None = None,
                      user_id: int | None = None, create_invoice: bool = True,
                      invoice_type: str = "standard", source_type: str = "pos",
                      source_id: int | None = None, allow_negative_stock: bool = False,
                      timestamp: str | None = None, audit=None,
                      date: str | None = None) -> dict:
        """Persist a sale and every derived record in one transaction."""
        items = list(items)
        if not items:
            raise ValueError("Le panier est vide")

        totals = cart_totals(items, Decimal(discount_percent_bp) / 100,
                             cents_to_money(discount_cents))
        stamp = timestamp or date or now_iso()
        total_cents = totals["total_ttc_cents"]

        if payment_method == "credit" and not customer_id:
            raise ValueError("Un client est obligatoire pour une vente \u00e0 cr\u00e9dit")

        # pre-flight stock check so nothing is written when it must fail
        for item in items:
            if item.track_stock and item.ref_id:
                available = self.stock.on_hand(item.ref_id)
                if available < qty_to_db(item.qty) and not allow_negative_stock:
                    raise StockError(f"Stock insuffisant pour '{item.label}'")

        with self.db.transaction():
            number = self.numbering.next_number("sale", stamp)
            paid_cents = self._paid_from_payments(payments, amount_received_cents, total_cents,
                                                  payment_method)
            change_cents = max(0, paid_cents - total_cents) if payment_method == "cash" else 0
            recorded_paid = min(paid_cents, total_cents) if payment_method != "credit" else 0

            sale_id = self.db.insert(
                "sales", number=number, date=stamp, customer_id=customer_id,
                cash_session_id=cash_session_id, source_type=source_type, source_id=source_id,
                subtotal_cents=totals["subtotal_ht_cents"], discount_cents=totals["discount_cents"],
                discount_percent_bp=int(discount_percent_bp),
                total_ht_cents=totals["total_ht_cents"], total_vat_cents=totals["total_vat_cents"],
                total_cents=total_cents, paid_cents=recorded_paid, change_cents=change_cents,
                payment_method=payment_method, cost_cents=self._cost_of(items), notes=notes,
                is_return=0, created_by=user_id, status="validated")

            self._write_items("sale_items", sale_id, items, totals)
            self._write_payments(sale_id, payments, payment_method, paid_cents, user_id)

            for item in items:
                if item.track_stock and item.ref_id:
                    self.stock.move(item.ref_id, -to_decimal(item.qty), "sale",
                                    ref_type="sale", ref_id=sale_id, ref_number=number,
                                    unit_cost_cents=item.cost_cents, user_id=user_id,
                                    allow_negative=allow_negative_stock, timestamp=stamp)

            invoice_id = None
            if create_invoice:
                invoice_id = self.create_invoice_from_sale(
                    sale_id, invoice_type=invoice_type, paid_cents=recorded_paid,
                    user_id=user_id, timestamp=stamp)
                self.db.update("sales", sale_id, invoice_id=invoice_id)

            if payment_method == "credit" and customer_id:
                self.parties.adjust_customer_balance(customer_id, total_cents)

            if cash_session_id:
                self._cash_movement(cash_session_id, "sale", "in", recorded_paid,
                                    "cash" if payment_method == "cash" else payment_method,
                                    "sale", sale_id, number, user_id, stamp)

            if audit:
                audit("sale.create", entity_type="sale", entity_id=sale_id,
                      details=f"{number} total={cents_to_money(total_cents)} "
                              f"method={payment_method}")

        return self.get_sale(sale_id)

    def _paid_from_payments(self, payments, amount_received_cents, total_cents,
                            payment_method) -> int:
        if payments:
            return sum(int(p.get("amount_cents", 0)) for p in payments)
        if payment_method == "credit":
            return 0
        if amount_received_cents:
            return int(amount_received_cents)
        return int(total_cents)

    def _cost_of(self, items) -> int:
        return sum(int(round(item.cost_cents * float(to_decimal(item.qty)))) for item in items)

    def _write_items(self, table: str, parent_id: int, items, totals: dict) -> list[int]:
        parent_column = table[:-1] if not table.endswith("s") else table[:-1]
        parent_column = {"sale_items": "sale_id", "invoice_items": "invoice_id",
                         "quote_items": "quote_id", "order_items": "order_id",
                         "credit_note_items": "credit_note_id",
                         "repair_items": "repair_id"}.get(table, parent_column)
        ids: list[int] = []
        prorated = totals.get("prorated_discount", {})
        available = self.db.table_columns(table)
        for index, item in enumerate(items):
            line = item.to_line()
            effective_net = money_to_cents(line.net_ht) - money_to_cents(
                prorated.get(index, Decimal(0)))
            vat_cents = int(round(effective_net * item.vat_rate_bp / 10000))
            row = {
                parent_column: parent_id,
                "code": item.code, "label": item.label, "unit": item.unit,
                "quantity": qty_to_db(item.qty),
                "unit_price_cents": item.unit_price_cents,
                "vat_rate_bp": item.vat_rate_bp,
                "line_ht_cents": effective_net,
                "line_vat_cents": vat_cents,
                "line_total_cents": effective_net + vat_cents,
                "sort_order": index,
            }
            for key, value in (
                    ("ref_type", item.ref_type),
                    ("product_id", item.ref_id if item.ref_type == "product" else None),
                    ("service_id", item.ref_id if item.ref_type == "service" else None),
                    ("discount_percent_bp", item.discount_percent_bp),
                    ("discount_cents", money_to_cents(line.discount_amount)
                     + money_to_cents(prorated.get(index, Decimal(0)))),
                    ("cost_cents", item.cost_cents)):
                if key in available:
                    row[key] = value
            ids.append(self.db.insert(table, **row))
        return ids

    def _write_payments(self, sale_id: int, payments, payment_method: str, paid_cents: int,
                        user_id: int | None) -> None:
        if payments:
            for payment in payments:
                self.db.insert("sale_payments", sale_id=sale_id,
                               method=payment.get("method", "cash"),
                               amount_cents=int(payment.get("amount_cents", 0)),
                               reference=payment.get("reference", ""), created_by=user_id)
        elif paid_cents > 0:
            self.db.insert("sale_payments", sale_id=sale_id, method=payment_method,
                           amount_cents=paid_cents, created_by=user_id)

    def _cash_movement(self, session_id: int, movement_type: str, direction: str,
                       amount_cents: int, method: str, ref_type: str, ref_id: int | None,
                       ref_number: str, user_id: int | None, stamp: str | None = None) -> None:
        if not amount_cents or method != "cash":
            return
        self.db.insert("cash_movements", session_id=session_id, date=stamp or now_iso(),
                       movement_type=movement_type, direction=direction,
                       amount_cents=int(amount_cents), method="cash", ref_type=ref_type,
                       ref_id=ref_id, ref_number=ref_number, created_by=user_id)

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    def get_sale(self, sale_id: int) -> dict:
        sale = self.db.fetch("sales", sale_id)
        if not sale:
            return {}
        sale["items"] = [dict(r) for r in self.db.query(
            "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY sort_order, id", (sale_id,))]
        sale["payments"] = [dict(r) for r in self.db.query(
            "SELECT * FROM sale_payments WHERE sale_id = ?", (sale_id,))]
        sale["customer"] = (self.db.fetch("customers", sale["customer_id"])
                            if sale.get("customer_id") else {})
        sale["totals"] = {
            "total_ht": cents_to_money(sale["total_ht_cents"]),
            "total_vat": cents_to_money(sale["total_vat_cents"]),
            "total_ttc": cents_to_money(sale["total_cents"]),
            "subtotal_ht": cents_to_money(sale["subtotal_cents"]),
            "discount": cents_to_money(sale["discount_cents"]),
        }
        sale["vat_breakdown"] = self.vat_breakdown(sale["items"])
        return sale

    @staticmethod
    def vat_breakdown(items: list[dict]) -> dict:
        breakdown: dict[str, int] = {}
        for item in items:
            rate = f"{Decimal(int(item.get('vat_rate_bp', 0))) / Decimal(100):.2f}"
            breakdown[rate] = breakdown.get(rate, 0) + int(item.get("line_vat_cents", 0))
        return {rate: cents_to_money(cents) for rate, cents in sorted(breakdown.items())}

    def list_sales(self, date_from: str = "", date_to: str = "", customer_id: int | None = None,
                   limit: int = 500, cash_session_id: int | None = None) -> list[dict]:
        sql = """SELECT s.*, c.name AS customer_name, u.username,
                        (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.id) AS items_count
                 FROM sales s
                 LEFT JOIN customers c ON c.id = s.customer_id
                 LEFT JOIN users u ON u.id = s.created_by
                 WHERE 1=1"""
        params: list = []
        if date_from:
            sql += " AND s.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND s.date <= ?"
            params.append(date_to + " 23:59:59")
        if customer_id:
            sql += " AND s.customer_id = ?"
            params.append(customer_id)
        if cash_session_id:
            sql += " AND s.cash_session_id = ?"
            params.append(cash_session_id)
        sql += " ORDER BY s.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    # ------------------------------------------------------------------
    # invoicing
    # ------------------------------------------------------------------
    def create_invoice_from_sale(self, sale_id: int, invoice_type: str = "standard",
                                 paid_cents: int | None = None, user_id: int | None = None,
                                 timestamp: str | None = None) -> int:
        sale = self.db.fetch("sales", sale_id)
        if not sale:
            raise ValueError("vente introuvable")
        existing = sale.get("invoice_id")
        if existing:
            return int(existing)

        stamp = timestamp or now_iso()
        due_days = 30 if invoice_type == "credit" else 0
        due_date = ((datetime.fromisoformat(stamp.replace(" ", "T")) +
                     timedelta(days=due_days)).date().isoformat() if due_days else "")
        paid = sale["paid_cents"] if paid_cents is None else int(paid_cents)
        if invoice_type == "credit":
            paid = 0
        total = int(sale["total_cents"])
        status = ("paid" if paid >= total and total > 0
                  else "partial" if paid > 0 else "unpaid")

        doc_type = "invoice_proforma" if invoice_type == "proforma" else "invoice"
        with self.db.transaction():
            number = self.numbering.next_number(doc_type, stamp)
            invoice_id = self.db.insert(
                "invoices", number=number, date=stamp, due_date=due_date,
                customer_id=sale.get("customer_id"), invoice_type=invoice_type,
                source_type="sale", source_id=sale_id, subtotal_cents=sale["subtotal_cents"],
                discount_cents=sale["discount_cents"], total_ht_cents=sale["total_ht_cents"],
                total_vat_cents=sale["total_vat_cents"], total_cents=total, paid_cents=paid,
                payment_method=sale.get("payment_method", ""), created_by=user_id, status=status)
            for item in self.db.query("SELECT * FROM sale_items WHERE sale_id = ? "
                                      "ORDER BY sort_order, id", (sale_id,)):
                self.db.insert(
                    "invoice_items", invoice_id=invoice_id, ref_type=item["ref_type"],
                    product_id=item["product_id"], service_id=item["service_id"],
                    code=item["code"], label=item["label"], unit=item["unit"],
                    quantity=item["quantity"], unit_price_cents=item["unit_price_cents"],
                    vat_rate_bp=item["vat_rate_bp"],
                    discount_percent_bp=item["discount_percent_bp"],
                    discount_cents=item["discount_cents"], line_ht_cents=item["line_ht_cents"],
                    line_vat_cents=item["line_vat_cents"],
                    line_total_cents=item["line_total_cents"], cost_cents=item["cost_cents"],
                    sort_order=item["sort_order"])
        return invoice_id

    # ------------------------------------------------------------------
    # held sales
    # ------------------------------------------------------------------
    def hold(self, items, customer_id: int | None, label: str = "",
             cash_session_id: int | None = None, user_id: int | None = None,
             discount_percent_bp: int = 0, discount_cents: int = 0) -> int:
        payload = {
            "items": [item.as_dict() for item in items],
            "discount_percent_bp": discount_percent_bp,
            "discount_cents": discount_cents,
        }
        return self.db.insert("held_sales", label=label or f"Vente en attente {now_iso()}",
                              customer_id=customer_id, payload=json.dumps(payload),
                              cash_session_id=cash_session_id, created_by=user_id,
                              status="held")

    def held_list(self, cash_session_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM held_sales WHERE status='held'"
        params: list = []
        if cash_session_id:
            sql += " AND (cash_session_id = ? OR cash_session_id IS NULL)"
            params.append(cash_session_id)
        sql += " ORDER BY id DESC"
        rows = [dict(r) for r in self.db.query(sql, params)]
        for row in rows:
            try:
                payload = json.loads(row["payload"])
                row["items"] = [CartItem.from_dict(data) for data in payload.get("items", [])]
                row["discount_percent_bp"] = payload.get("discount_percent_bp", 0)
                row["discount_cents"] = payload.get("discount_cents", 0)
            except json.JSONDecodeError:
                row["items"] = []
        return rows

    def release_held(self, held_id: int) -> dict:
        row = self.db.fetch("held_sales", held_id)
        if not row:
            return {}
        self.db.update("held_sales", held_id, status="resumed")
        payload = json.loads(row["payload"])
        return {
            "items": [CartItem.from_dict(data) for data in payload.get("items", [])],
            "customer_id": row.get("customer_id"),
            "discount_percent_bp": payload.get("discount_percent_bp", 0),
            "discount_cents": payload.get("discount_cents", 0),
        }

    def cancel_held(self, held_id: int) -> None:
        self.db.update("held_sales", held_id, status="cancelled")

    # ------------------------------------------------------------------
    # returns / refunds
    # ------------------------------------------------------------------
    def returnable_quantity(self, sale_id: int, product_id: int) -> Decimal:
        item = self.db.query_one(
            "SELECT quantity FROM sale_items WHERE sale_id=? AND product_id=? AND ref_type='product'",
            (sale_id, product_id))
        if not item:
            return Decimal(0)
        returned = int(self.db.scalar(
            """SELECT COALESCE(SUM(ri.quantity),0) FROM return_items ri
               JOIN return_notes rn ON rn.id = ri.return_id
               WHERE rn.source_type='sale' AND rn.source_id=? AND ri.product_id=?
                 AND rn.status <> 'cancelled'""", (sale_id, product_id), default=0))
        return db_to_qty(int(item["quantity"]) - returned)

    def create_return(self, sale_id: int, returns: list[dict], *, reason: str = "",
                      condition_code: str = "good", restock: bool = True,
                      user_id: int | None = None, numbering=None, audit=None,
                      refund_method: str = "cash", cash_session_id: int | None = None,
                      timestamp: str | None = None) -> dict:
        """Create a customer return note, restock and issue a credit note.

        ``returns`` is a list of ``{"product_id": int, "qty": Decimal, "reason": str}``.
        """
        sale = self.db.fetch("sales", sale_id)
        if not sale:
            raise ValueError("vente introuvable")
        stamp = timestamp or now_iso()
        numbering = numbering or self.numbering

        with self.db.transaction():
            number = numbering.next_number("return_client", stamp)
            return_id = self.db.insert(
                "return_notes", number=number, date=stamp, direction="client",
                party_id=sale.get("customer_id"), source_type="sale", source_id=sale_id,
                source_number=sale["number"], reason=reason, condition_code=condition_code,
                created_by=user_id, status="draft")

            refund_total_ht = 0
            refund_total_vat = 0
            for entry in returns:
                product_id = int(entry["product_id"])
                requested = qty_to_db(entry.get("qty", 1))
                if requested <= 0:
                    continue
                available = qty_to_db(self.returnable_quantity(sale_id, product_id))
                if requested > available:
                    raise ValueError(
                        f"Quantit\u00e9 retourn\u00e9e sup\u00e9rieure \u00e0 la quantit\u00e9 vendue "
                        f"(max {db_to_qty(available)})")
                item = self.db.query_one(
                    "SELECT * FROM sale_items WHERE sale_id=? AND product_id=?",
                    (sale_id, product_id))
                unit_price = int(item["unit_price_cents"])
                vat_bp = int(item["vat_rate_bp"])
                line_ht = int(round(requested / 1000 * unit_price))
                line_vat = int(round(line_ht * vat_bp / 10000))
                self.db.insert(
                    "return_items", return_id=return_id, ref_type="product",
                    product_id=product_id, code=item["code"], label=item["label"],
                    unit=item["unit"], quantity=requested, unit_price_cents=unit_price,
                    vat_rate_bp=vat_bp, line_total_cents=line_ht + line_vat,
                    reason=entry.get("reason", reason), condition_code=condition_code,
                    restock=1 if (restock and entry.get("restock", True)) else 0)
                refund_total_ht += line_ht
                refund_total_vat += line_vat
                if restock and entry.get("restock", True):
                    self.stock.move(product_id, db_to_qty(requested), "return_client",
                                    ref_type="return", ref_id=return_id, ref_number=number,
                                    unit_cost_cents=int(item["cost_cents"]),
                                    reason=reason, user_id=user_id, timestamp=stamp)

            refund_cents = refund_total_ht + refund_total_vat
            self.db.update("return_notes", return_id, refund_cents=refund_cents,
                           status="validated")

            credit_note_id = None
            if refund_cents > 0:
                credit_note_id = self.db.insert(
                    "credit_notes", number=numbering.next_number("credit_note", stamp),
                    date=stamp, customer_id=sale.get("customer_id"),
                    invoice_id=sale.get("invoice_id"), return_id=return_id, reason=reason,
                    total_ht_cents=refund_total_ht, total_vat_cents=refund_total_vat,
                    total_cents=refund_cents, created_by=user_id, status="validated")
                for row in self.db.query("SELECT * FROM return_items WHERE return_id=?",
                                         (return_id,)):
                    line_ht = int(row["line_total_cents"]) - int(
                        round(row["line_total_cents"] * row["vat_rate_bp"] / (10000 + row["vat_rate_bp"])))
                    self.db.insert(
                        "credit_note_items", credit_note_id=credit_note_id,
                        ref_type="product", product_id=row["product_id"], code=row["code"],
                        label=row["label"], unit=row["unit"], quantity=row["quantity"],
                        unit_price_cents=row["unit_price_cents"],
                        vat_rate_bp=row["vat_rate_bp"], line_ht_cents=line_ht,
                        line_vat_cents=int(row["line_total_cents"]) - line_ht,
                        line_total_cents=int(row["line_total_cents"]))

                if sale.get("customer_id"):
                    self.parties.adjust_customer_balance(sale["customer_id"], -refund_cents)
                if sale.get("invoice_id"):
                    self._apply_credit_to_invoice(sale["invoice_id"], refund_cents)

            if cash_session_id and refund_method == "cash":
                self.db.insert("cash_movements", session_id=cash_session_id, date=stamp,
                               movement_type="refund", direction="out",
                               amount_cents=refund_cents, method="cash", ref_type="return",
                               ref_id=return_id, ref_number=number, created_by=user_id)

            if audit:
                audit("sale.refund", entity_type="return_note", entity_id=return_id,
                      details=f"{number} vente={sale['number']} montant={refund_cents / 100}")

        return {"return_id": return_id, "number": number, "refund_cents": refund_cents,
                "credit_note_id": credit_note_id}

    def _apply_credit_to_invoice(self, invoice_id: int, amount_cents: int) -> None:
        invoice = self.db.fetch("invoices", invoice_id)
        if not invoice:
            return
        paid = int(invoice["paid_cents"]) + int(amount_cents)
        total = int(invoice["total_cents"])
        status = "paid" if paid >= total else "partial" if paid > 0 else "unpaid"
        self.db.update("invoices", invoice_id, paid_cents=min(paid, total), status=status)

    # ------------------------------------------------------------------
    # statistics used by the dashboard and reports
    # ------------------------------------------------------------------
    def totals_for_period(self, date_from: str, date_to: str) -> dict:
        row = self.db.query_one(
            """SELECT COUNT(*) AS count,
                      COALESCE(SUM(CASE WHEN is_return=0 THEN total_cents ELSE -total_cents END),0) AS turnover,
                      COALESCE(SUM(CASE WHEN is_return=0 THEN total_ht_cents ELSE -total_ht_cents END),0) AS turnover_ht,
                      COALESCE(SUM(CASE WHEN is_return=0 THEN cost_cents ELSE -cost_cents END),0) AS cost
               FROM sales WHERE status='validated' AND date >= ? AND date <= ?""",
            (date_from, date_to + " 23:59:59"))
        data = dict(row) if row else {}
        turnover_ht = int(data.get("turnover_ht", 0))
        cost = int(data.get("cost", 0))
        data["profit_cents"] = turnover_ht - cost
        data["turnover_money"] = cents_to_money(data.get("turnover", 0))
        data["profit_money"] = cents_to_money(data["profit_cents"])
        return data

    def daily_series(self, days: int = 30) -> list[dict]:
        rows = self.db.query(
            """SELECT substr(date,1,10) AS day,
                      COALESCE(SUM(CASE WHEN is_return=0 THEN total_cents ELSE -total_cents END),0) AS turnover,
                      COALESCE(SUM(CASE WHEN is_return=0 THEN total_ht_cents-cost_cents
                                        ELSE -(total_ht_cents-cost_cents) END),0) AS profit
               FROM sales WHERE status='validated' AND date >= date('now', ?)
               GROUP BY day ORDER BY day""", (f"-{int(days)} days",))
        return [{"day": r["day"], "turnover": cents_to_money(r["turnover"]),
                 "profit": cents_to_money(r["profit"])} for r in rows]

    def top_products(self, date_from: str = "", date_to: str = "", limit: int = 10) -> list[dict]:
        sql = """SELECT si.code, si.label,
                        COALESCE(SUM(si.quantity),0) AS quantity,
                        COALESCE(SUM(si.line_total_cents),0) AS revenue,
                        COALESCE(SUM(si.line_ht_cents - si.cost_cents*si.quantity/1000),0) AS profit
                 FROM sale_items si JOIN sales s ON s.id = si.sale_id
                 WHERE s.status='validated'"""
        params: list = []
        if date_from:
            sql += " AND s.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND s.date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " GROUP BY si.code, si.label ORDER BY revenue DESC LIMIT ?"
        params.append(int(limit))
        rows = [dict(r) for r in self.db.query(sql, params)]
        for row in rows:
            row["quantity_display"] = db_to_qty(row["quantity"])
            row["revenue_money"] = cents_to_money(row["revenue"])
            row["profit_money"] = cents_to_money(row["profit"])
        return rows

    def sales_by_category(self, date_from: str = "", date_to: str = "") -> list[dict]:
        sql = """SELECT COALESCE(c.name,'Sans cat\u00e9gorie') AS category,
                        COALESCE(SUM(si.line_total_cents),0) AS revenue,
                        COALESCE(SUM(si.quantity),0) AS quantity
                 FROM sale_items si
                 JOIN sales s ON s.id = si.sale_id
                 LEFT JOIN products p ON p.id = si.product_id
                 LEFT JOIN categories c ON c.id = p.category_id
                 WHERE s.status='validated'"""
        params: list = []
        if date_from:
            sql += " AND s.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND s.date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " GROUP BY c.name ORDER BY revenue DESC"
        rows = [dict(r) for r in self.db.query(sql, params)]
        for row in rows:
            row["revenue_money"] = cents_to_money(row["revenue"])
            row["quantity_display"] = db_to_qty(row["quantity"])
        return rows

    def sales_by_payment_method(self, date_from: str = "", date_to: str = "") -> list[dict]:
        sql = """SELECT payment_method, COUNT(*) AS count,
                        COALESCE(SUM(total_cents),0) AS revenue
                 FROM sales WHERE status='validated'"""
        params: list = []
        if date_from:
            sql += " AND date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " GROUP BY payment_method ORDER BY revenue DESC"
        rows = [dict(r) for r in self.db.query(sql, params)]
        for row in rows:
            row["revenue_money"] = cents_to_money(row["revenue"])
        return rows
