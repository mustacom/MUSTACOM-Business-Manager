"""Stock ledger.

``products.stock`` is the cached on-hand quantity; ``stock_movements`` is the
authoritative journal.  Every mutation of on-hand stock goes through
:func:`StockService.move`, which writes the journal line (with before/after
quantities) in the same transaction as the document that caused it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from ..config import STOCK_MOVEMENT_TYPES
from ..db.database import Database, now_iso
from .money import cents_to_money, db_to_qty, money_to_cents, qty_to_db, to_decimal


class StockError(RuntimeError):
    pass


class StockService:
    def __init__(self, db: Database):
        self.db = db

    # -- low level ----------------------------------------------------------
    def on_hand(self, product_id: int) -> int:
        return int(self.db.scalar("SELECT stock FROM products WHERE id = ?",
                                  (product_id,), default=0))

    def move(self, product_id: int, quantity, movement_type: str, *,
             ref_type: str = "", ref_id: int | None = None, ref_number: str = "",
             unit_cost_cents: int = 0, location_from: str = "", location_to: str = "",
             reason: str = "", notes: str = "", user_id: int | None = None,
             allow_negative: bool = False, timestamp: str | None = None) -> dict:
        """Apply a signed quantity change and journal it.

        ``quantity`` is expressed in *units* (int/float/Decimal/str); it is
        converted to milli-units for storage.  Sales and exits pass a negative
        number.
        """
        if movement_type not in STOCK_MOVEMENT_TYPES:
            raise StockError(f"type de mouvement inconnu: {movement_type}")
        delta = qty_to_db(quantity)
        product = self.db.fetch("products", product_id)
        if not product:
            raise StockError(f"produit {product_id} introuvable")

        before = int(product["stock"])
        after = before + delta
        # The guard only applies to *outbound* movements: receiving goods can
        # never make the stock go negative.
        if (delta < 0 and after < 0 and not allow_negative
                and int(product.get("track_stock", 1))):
            raise StockError(
                f"Stock insuffisant pour '{product['name']}' "
                f"(disponible {db_to_qty(before)}, demand\u00e9 {db_to_qty(abs(delta))})")

        with self.db.transaction():
            self.db.execute("UPDATE products SET stock = ?, updated_at = ? WHERE id = ?",
                            (after, now_iso(), product_id))
            movement_id = self.db.insert(
                "stock_movements",
                date=timestamp or now_iso(),
                product_id=product_id,
                movement_type=movement_type,
                quantity=delta,
                qty_before=before,
                qty_after=after,
                unit_cost_cents=int(unit_cost_cents),
                location_from=location_from or product.get("location", ""),
                location_to=location_to or product.get("location", ""),
                ref_type=ref_type,
                ref_id=ref_id,
                ref_number=ref_number,
                reason=reason,
                notes=notes,
                created_by=user_id,
                status="validated",
            )
        return {"id": movement_id, "before": before, "after": after, "delta": delta}

    def set_stock(self, product_id: int, target_quantity, movement_type: str = "adjustment",
                  **kwargs) -> dict:
        """Force the on-hand quantity, journalling the difference."""
        target = qty_to_db(target_quantity)
        delta = target - self.on_hand(product_id)
        if delta == 0:
            return {"id": None, "before": target, "after": target, "delta": 0}
        return self.move(product_id, db_to_qty(delta), movement_type, **kwargs)

    def transfer(self, product_id: int, quantity, location_from: str, location_to: str,
                 user_id: int | None = None, notes: str = "") -> dict:
        """Move stock between two physical locations (quantity unchanged)."""
        product = self.db.fetch("products", product_id)
        if not product:
            raise StockError(f"produit {product_id} introuvable")
        delta = qty_to_db(quantity)
        with self.db.transaction():
            movement_id = self.db.insert(
                "stock_movements", date=now_iso(), product_id=product_id,
                movement_type="transfer", quantity=0,
                qty_before=int(product["stock"]), qty_after=int(product["stock"]),
                unit_cost_cents=int(product.get("purchase_price_cents", 0)),
                location_from=location_from, location_to=location_to,
                ref_type="transfer", notes=notes, created_by=user_id, status="validated")
            self.db.execute("UPDATE products SET location = ?, updated_at = ? WHERE id = ?",
                            (location_to, now_iso(), product_id))
        return {"id": movement_id, "delta": delta}

    # -- queries ------------------------------------------------------------
    def movements(self, product_id: int | None = None, limit: int = 500,
                  movement_type: str = "", date_from: str = "", date_to: str = "") -> list[dict]:
        sql = """SELECT sm.*, p.sku, p.name AS product_name, u.username
                 FROM stock_movements sm
                 JOIN products p ON p.id = sm.product_id
                 LEFT JOIN users u ON u.id = sm.created_by
                 WHERE 1=1"""
        params: list = []
        if product_id is not None:
            sql += " AND sm.product_id = ?"
            params.append(product_id)
        if movement_type:
            sql += " AND sm.movement_type = ?"
            params.append(movement_type)
        if date_from:
            sql += " AND sm.date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND sm.date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " ORDER BY sm.id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self.db.query(sql, params)]

    def low_stock(self, only_out: bool = False) -> list[dict]:
        sql = """SELECT p.*, c.name AS category_name, s.name AS supplier_name
                 FROM products p
                 LEFT JOIN categories c ON c.id = p.category_id
                 LEFT JOIN suppliers s ON s.id = p.supplier_id
                 WHERE p.is_active = 1 AND p.track_stock = 1"""
        sql += " AND p.stock <= 0" if only_out else " AND p.stock <= p.stock_min"
        sql += " ORDER BY p.stock ASC, p.name"
        return [dict(r) for r in self.db.query(sql)]

    def valuation(self) -> dict:
        row = self.db.query_one("""
            SELECT COUNT(*) AS products,
                   COALESCE(SUM(CASE WHEN stock > 0 THEN 1 ELSE 0 END),0) AS in_stock,
                   COALESCE(SUM(CASE WHEN stock <= 0 THEN 1 ELSE 0 END),0) AS out_of_stock,
                   COALESCE(SUM(CASE WHEN stock > 0 AND stock <= stock_min THEN 1 ELSE 0 END),0) AS low,
                   COALESCE(SUM(stock * purchase_price_cents),0) AS value_purchase,
                   COALESCE(SUM(stock * sale_price_cents),0) AS value_sale
            FROM products WHERE is_active = 1""")
        data = dict(row) if row else {}
        data["value_purchase_money"] = cents_to_money(data.get("value_purchase", 0))
        data["value_sale_money"] = cents_to_money(data.get("value_sale", 0))
        data["potential_margin_money"] = cents_to_money(
            data.get("value_sale", 0) - data.get("value_purchase", 0))
        return data

    def movement_summary(self, date_from: str = "", date_to: str = "") -> list[dict]:
        sql = """SELECT movement_type, COUNT(*) AS count,
                        COALESCE(SUM(quantity),0) AS quantity
                 FROM stock_movements WHERE 1=1"""
        params: list = []
        if date_from:
            sql += " AND date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date <= ?"
            params.append(date_to + " 23:59:59")
        sql += " GROUP BY movement_type ORDER BY movement_type"
        return [dict(r) for r in self.db.query(sql, params)]

    # -- physical inventory -------------------------------------------------
    def start_inventory(self, location: str = "", user_id: int | None = None,
                        numbering=None) -> dict:
        number = numbering.next_number("inventory") if numbering else f"INV-{datetime.now().year}-0001"
        with self.db.transaction():
            inventory_id = self.db.insert("inventories", number=number, date=now_iso(),
                                          location=location, created_by=user_id, status="draft")
            products = self.db.query(
                "SELECT id, stock FROM products WHERE is_active=1 AND track_stock=1 "
                + ("AND location = ?" if location else "") + " ORDER BY sku",
                (location,) if location else ())
            for product in products:
                self.db.insert("inventory_items", inventory_id=inventory_id,
                               product_id=product["id"], expected_qty=int(product["stock"]),
                               counted_qty=None, difference=0, applied=0)
        return self.db.fetch("inventories", inventory_id)

    def inventory_items(self, inventory_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            """SELECT ii.*, p.sku, p.name, p.unit, p.purchase_price_cents, p.sale_price_cents
               FROM inventory_items ii JOIN products p ON p.id = ii.product_id
               WHERE ii.inventory_id = ? ORDER BY p.sku""", (inventory_id,))]

    def set_counted(self, item_id: int, counted_qty) -> None:
        counted = qty_to_db(counted_qty)
        item = self.db.fetch("inventory_items", item_id)
        if not item:
            return
        self.db.update("inventory_items", item_id, counted_qty=counted,
                       difference=counted - int(item["expected_qty"]))

    def apply_inventory(self, inventory_id: int, user_id: int | None = None,
                        allow_negative: bool = False) -> int:
        """Post the counted differences as adjustment movements."""
        items = self.inventory_items(inventory_id)
        inventory = self.db.fetch("inventories", inventory_id)
        applied = 0
        with self.db.transaction():
            for item in items:
                if item["counted_qty"] is None or item["applied"]:
                    continue
                difference = int(item["difference"])
                if difference:
                    self.move(item["product_id"], db_to_qty(difference), "inventory",
                              ref_type="inventory", ref_id=inventory_id,
                              ref_number=inventory["number"],
                              unit_cost_cents=int(item.get("purchase_price_cents", 0)),
                              reason="Inventaire physique", user_id=user_id,
                              allow_negative=allow_negative)
                self.db.update("inventory_items", item["id"], applied=1)
                applied += 1
            self.db.update("inventories", inventory_id, status="validated")
        return applied
