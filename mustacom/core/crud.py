"""Catalogue CRUD: products, categories, brands, customers, suppliers, services.

Each service validates its input, keeps derived values consistent (for example
``price_ttc`` follows ``price_ht`` and the VAT rate) and never trusts the
caller: every value is normalised before it reaches SQL.
"""

from __future__ import annotations

import csv
import io
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ..db.database import Database, now_iso
from .money import (cents_to_money, money_to_cents, price_with_markup, qty_to_db,
                    rate_to_db, to_decimal)
from .security import (ValidationError, clean_text, validate_email, validate_ice,
                       validate_percent, validate_phone, validate_positive_number)

DEFAULT_CATEGORY_SEED = [
    ("BUREAU", "Fourniture de bureau", "product"),
    ("SCOLAIRE", "Fourniture scolaire", "product"),
    ("INFORMATIQUE", "Informatique", "product"),
    ("LIBRAIRIE", "Librairie", "product"),
    ("IMPRESSION", "Impression", "product"),
    ("ACCESSOIRES", "Accessoires", "product"),
    ("PAPETERIE", "Papeterie", "product"),
    ("CARTOUCHES", "Cartouches et toners", "product"),
    ("CONSOMMABLES", "Consommables", "product"),
    ("AUTRES", "Autres", "product"),
    ("SVC_IMPRESSION", "Impression & photocopie", "service"),
    ("SVC_NUMERIQUE", "Services num\u00e9riques", "service"),
    ("SVC_PUBLICITE", "Publicit\u00e9", "service"),
    ("SVC_REPARATION", "R\u00e9paration", "service"),
    ("EXP", "D\u00e9penses", "expense"),
]

DEFAULT_SERVICE_SEED = [
    ("SVC-PHOTO-NB", "Photocopie N/B", "u", 0, 50, 20),
    ("SVC-PHOTO-COUL", "Photocopie couleur", "u", 0, 200, 20),
    ("SVC-IMP-NB", "Impression noir et blanc", "u", 0, 100, 20),
    ("SVC-IMP-COUL", "Impression couleur", "u", 0, 300, 20),
    ("SVC-IMP-GRAND", "Impression grand format", "m\u00b2", 0, 8000, 20),
    ("SVC-IMP-THERM", "Impression thermique", "u", 0, 150, 20),
    ("SVC-REL", "Reliure", "u", 0, 1000, 20),
    ("SVC-PLAST", "Plastification", "u", 0, 500, 20),
    ("SVC-SCAN", "Scan", "u", 0, 100, 20),
    ("SVC-SAISIE", "Saisie de document", "page", 0, 500, 20),
    ("SVC-MEP", "Mise en page", "heure", 0, 10000, 20),
    ("SVC-GRAPH", "Cr\u00e9ation graphique", "heure", 0, 20000, 20),
    ("SVC-PUB", "Impression publicitaire", "m\u00b2", 0, 15000, 20),
    ("SVC-GRAV", "Gravure", "u", 0, 5000, 20),
    ("SVC-REP-PC", "R\u00e9paration ordinateur", "heure", 0, 15000, 20),
    ("SVC-INST-OS", "Installation syst\u00e8me", "u", 0, 25000, 20),
    ("SVC-MAINT", "Maintenance informatique", "mois", 0, 30000, 20),
    ("SVC-AUTRE", "Autres services", "u", 0, 0, 20),
]


# ---------------------------------------------------------------------------
class CatalogService:
    def __init__(self, db: Database):
        self.db = db

    # -- seed ---------------------------------------------------------------
    def seed_defaults(self) -> None:
        for code, name, kind in DEFAULT_CATEGORY_SEED:
            if not self.db.scalar("SELECT id FROM categories WHERE code = ?", (code,)):
                self.db.insert("categories", code=code, name=name, kind=kind, is_active=1,
                               sort_order=0, status="active")
        for code, name, unit, cost, price, vat in DEFAULT_SERVICE_SEED:
            if not self.db.scalar("SELECT id FROM services WHERE code = ?", (code,)):
                category = self.db.scalar(
                    "SELECT id FROM categories WHERE code = 'SVC_IMPRESSION'")
                self.db.insert("services", code=code, name=name, unit=unit,
                               category_id=category, cost_cents=money_to_cents(cost),
                               price_cents=money_to_cents(price), vat_rate_bp=rate_to_db(vat),
                               is_active=1, status="active")

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------
    def categories(self, kind: str = "") -> list[dict]:
        sql = "SELECT * FROM categories WHERE is_active = 1"
        params: list = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY sort_order, name"
        return [dict(r) for r in self.db.query(sql, params)]

    def save_category(self, data: dict, category_id: int | None = None) -> int:
        code = data.get("code") or clean_text(data.get("name", "")).upper().replace(" ", "-")[:20]
        values = {
            "code": clean_text(code, 30),
            "name": clean_text(data.get("name"), 80),
            "kind": data.get("kind", "product"),
            "parent_id": data.get("parent_id") or None,
            "description": clean_text(data.get("description"), 250),
            "is_active": 1 if data.get("is_active", True) else 0,
            "sort_order": int(data.get("sort_order") or 0),
        }
        if not values["name"]:
            raise ValidationError("name", "nom de cat\u00e9gorie obligatoire")
        if category_id:
            self.db.update("categories", category_id, **values)
            return category_id
        return self.db.insert("categories", **values, status="active")

    def delete_category(self, category_id: int) -> None:
        self.db.update("categories", category_id, is_active=0, status="inactive")

    # ------------------------------------------------------------------
    # brands
    # ------------------------------------------------------------------
    def brands(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM brands WHERE is_active = 1 ORDER BY name")]

    def save_brand(self, name: str, brand_id: int | None = None) -> int:
        name = clean_text(name, 60)
        if not name:
            raise ValidationError("name", "nom de marque obligatoire")
        if brand_id:
            self.db.update("brands", brand_id, name=name)
            return brand_id
        existing = self.db.scalar("SELECT id FROM brands WHERE name = ?", (name,))
        if existing:
            return int(existing)
        return self.db.insert("brands", name=name, is_active=1, status="active")

    # ------------------------------------------------------------------
    # products
    # ------------------------------------------------------------------
    def products(self, term: str = "", category_id: int | None = None,
                 brand_id: int | None = None, stock_filter: str = "",
                 supplier_id: int | None = None, active_only: bool = True,
                 limit: int = 1000, offset: int = 0, order: str = "p.name") -> tuple[list[dict], int]:
        where = ["1=1"]
        params: list = []
        if active_only:
            where.append("p.is_active = 1")
        if term:
            like = f"%{term}%"
            where.append("(p.name LIKE ? OR p.sku LIKE ? OR p.barcode = ? OR p.reference LIKE ?)")
            params += [like, like, term, like]
        if category_id:
            where.append("(p.category_id = ? OR p.subcategory_id = ?)")
            params += [category_id, category_id]
        if brand_id:
            where.append("p.brand_id = ?")
            params.append(brand_id)
        if supplier_id:
            where.append("p.supplier_id = ?")
            params.append(supplier_id)
        if stock_filter == "out":
            where.append("p.stock <= 0")
        elif stock_filter == "low":
            where.append("p.stock > 0 AND p.stock <= p.stock_min")
        elif stock_filter == "ok":
            where.append("p.stock > p.stock_min")

        allowed_order = {
            "p.name", "p.name DESC", "p.sku", "p.sku DESC", "p.stock", "p.stock DESC",
            "p.sale_price_cents", "p.sale_price_cents DESC", "p.created_at DESC",
            "p.updated_at DESC",
        }
        order_clause = order if order in allowed_order else "p.name"
        clause = " AND ".join(where)
        total = int(self.db.scalar(f"SELECT COUNT(*) FROM products p WHERE {clause}",
                                   params, default=0))
        rows = self.db.query(
            f"""SELECT p.*, c.name AS category_name, sc.name AS subcategory_name,
                       b.name AS brand_name, s.name AS supplier_name
                FROM products p
                LEFT JOIN categories c ON c.id = p.category_id
                LEFT JOIN categories sc ON sc.id = p.subcategory_id
                LEFT JOIN brands b ON b.id = p.brand_id
                LEFT JOIN suppliers s ON s.id = p.supplier_id
                WHERE {clause} ORDER BY {order_clause} LIMIT ? OFFSET ?""",
            (*params, int(limit), int(offset)))
        return [dict(r) for r in rows], total

    def product(self, product_id: int) -> dict:
        row = self.db.query_one(
            """SELECT p.*, c.name AS category_name, b.name AS brand_name,
                      s.name AS supplier_name
               FROM products p
               LEFT JOIN categories c ON c.id = p.category_id
               LEFT JOIN brands b ON b.id = p.brand_id
               LEFT JOIN suppliers s ON s.id = p.supplier_id
               WHERE p.id = ?""", (product_id,))
        return dict(row) if row else {}

    def product_by_code(self, code: str) -> dict:
        row = self.db.query_one("SELECT * FROM products WHERE sku = ? OR barcode = ?",
                                (code, code))
        return dict(row) if row else {}

    def validate_product(self, data: dict) -> dict:
        sku = clean_text(data.get("sku"), 40)
        name = clean_text(data.get("name"), 200)
        if not sku:
            raise ValidationError("sku", "code produit obligatoire")
        if not name:
            raise ValidationError("name", "d\u00e9signation obligatoire")
        barcode = clean_text(data.get("barcode"), 40)
        return {
            "sku": sku,
            "barcode": barcode or None,
            "name": name,
            "category_id": data.get("category_id") or None,
            "subcategory_id": data.get("subcategory_id") or None,
            "brand_id": data.get("brand_id") or None,
            "reference": clean_text(data.get("reference"), 60),
            "unit": clean_text(data.get("unit"), 12) or "u",
            "purchase_price_cents": money_to_cents(
                validate_positive_number(data.get("purchase_price_cents", 0),
                                         "purchase_price_cents")),
            "sale_price_cents": money_to_cents(
                validate_positive_number(data.get("sale_price_cents", 0),
                                         "sale_price_cents")),
            "vat_rate_bp": rate_to_db(validate_percent(data.get("vat_rate_bp", 20), "vat")),
            "price_includes_vat": 1 if data.get("price_includes_vat") else 0,
            "stock": qty_to_db(validate_positive_number(data.get("stock", 0), "stock")),
            "stock_min": qty_to_db(validate_positive_number(data.get("stock_min", 0), "stock_min")),
            "stock_max": qty_to_db(validate_positive_number(data.get("stock_max", 0), "stock_max")),
            "location": clean_text(data.get("location"), 60),
            "supplier_id": data.get("supplier_id") or None,
            "image_path": clean_text(data.get("image_path"), 500),
            "description": clean_text(data.get("description"), 2000),
            "is_active": 1 if data.get("is_active", True) else 0,
            "track_stock": 1 if data.get("track_stock", True) else 0,
            "sellable": 1 if data.get("sellable", True) else 0,
        }

    def save_product(self, data: dict, product_id: int | None = None,
                     user_id: int | None = None, audit=None) -> int:
        values = self.validate_product(data)
        duplicate = self.db.scalar(
            "SELECT id FROM products WHERE sku = ? AND id <> ?",
            (values["sku"], product_id or 0))
        if duplicate:
            raise ValidationError("sku", f"le code {values['sku']} existe d\u00e9j\u00e0")
        if values["barcode"]:
            duplicate = self.db.scalar(
                "SELECT id FROM products WHERE barcode = ? AND id <> ?",
                (values["barcode"], product_id or 0))
            if duplicate:
                raise ValidationError("barcode", "ce code-barres est d\u00e9j\u00e0 utilis\u00e9")

        if product_id:
            before = self.product(product_id)
            self.db.update("products", product_id, **values)
            if audit and before and before.get("sale_price_cents") != values["sale_price_cents"]:
                audit("product.price_change", entity_type="product", entity_id=product_id,
                      details=f"{values['sku']}: {before['sale_price_cents'] / 100} -> "
                              f"{values['sale_price_cents'] / 100}")
            return product_id

        product_id = self.db.insert("products", **values, created_by=user_id, status="active")
        stock = values["stock"]
        if stock:
            self.db.execute(
                """INSERT INTO stock_movements
                   (date, product_id, movement_type, quantity, qty_before, qty_after,
                    unit_cost_cents, location_to, ref_type, reason, created_at, created_by, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (now_iso(), product_id, "initial", stock, 0, stock,
                 values["purchase_price_cents"], values["location"], "initial",
                 "Stock initial", now_iso(), user_id, "validated"))
        if audit:
            audit("product.create", entity_type="product", entity_id=product_id,
                  details=f"{values['sku']} - {values['name']}")
        return product_id

    def delete_product(self, product_id: int, audit=None) -> None:
        product = self.product(product_id)
        used = self.db.scalar(
            """SELECT (SELECT COUNT(*) FROM sale_items WHERE product_id = ?)
                    + (SELECT COUNT(*) FROM invoice_items WHERE product_id = ?)
                    + (SELECT COUNT(*) FROM purchase_items WHERE product_id = ?)""",
            (product_id, product_id, product_id), default=0)
        if used:
            # never destroy accounting history: deactivate instead
            self.db.update("products", product_id, is_active=0, status="inactive")
            if audit:
                audit("product.deactivate", entity_type="product", entity_id=product_id,
                      details=product.get("sku", ""))
            return
        self.db.execute("DELETE FROM stock_movements WHERE product_id = ?", (product_id,))
        self.db.delete("products", product_id)
        if audit:
            audit("product.delete", entity_type="product", entity_id=product_id,
                  details=product.get("sku", ""))

    def price_ttc(self, product: dict) -> Decimal:
        ht = cents_to_money(product.get("sale_price_cents", 0))
        rate = Decimal(int(product.get("vat_rate_bp", 0))) / Decimal(100)
        return (ht * (1 + rate / 100)).quantize(Decimal("0.01"))

    def suggest_price(self, cost, margin_percent=None, markup_percent=None) -> Decimal:
        if markup_percent is not None:
            return price_with_markup(cost, markup_percent)
        from .money import price_from_margin
        return price_from_margin(cost, margin_percent or 30)

    def generate_sku(self, prefix: str = "PRD") -> str:
        last = self.db.scalar("SELECT sku FROM products ORDER BY id DESC LIMIT 1")
        number = 1
        if last:
            tail = str(last)[-5:]
            if tail.isdigit():
                number = int(tail) + 1
        return f"{prefix}-{number:05d}"

    # -- import / export ----------------------------------------------------
    PRODUCT_IMPORT_COLUMNS = {
        "sku": "sku", "code": "sku", "code produit": "sku", "code_produit": "sku",
        "barcode": "barcode", "code-barres": "barcode", "code_barres": "barcode",
        "designation": "name", "d\u00e9signation": "name", "name": "name", "nom": "name",
        "category": "category", "cat\u00e9gorie": "category",
        "brand": "brand", "marque": "brand",
        "reference": "reference", "r\u00e9f\u00e9rence": "reference",
        "unit": "unit", "unit\u00e9": "unit",
        "purchase_price": "purchase_price", "prix achat": "purchase_price",
        "prix_achat": "purchase_price", "prix achat ht": "purchase_price",
        "sale_price": "sale_price", "prix vente": "sale_price", "prix_vente": "sale_price",
        "prix vente ht": "sale_price",
        "vat": "vat", "tva": "vat",
        "stock": "stock", "stock_min": "stock_min", "stock minimum": "stock_min",
        "stock_max": "stock_max", "location": "location", "emplacement": "location",
        "description": "description",
    }

    def import_products(self, path: Path | str, user_id: int | None = None,
                        dry_run: bool = False) -> dict:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        delimiter = ";" if text.count(";") > text.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        created = updated = errors = 0
        error_rows: list[str] = []
        default_vat = 20.0
        for index, raw in enumerate(reader, start=2):
            try:
                data: dict = {}
                for key, value in raw.items():
                    if key is None:
                        continue
                    mapped = self.PRODUCT_IMPORT_COLUMNS.get(str(key).strip().lower())
                    if mapped:
                        data[mapped] = (value or "").strip()
                if not data.get("sku") and not data.get("name"):
                    continue
                data["vat"] = data.get("vat") or default_vat
                data.setdefault("stock_min", 0)
                data.setdefault("stock_max", 0)
                if data.get("category"):
                    data["category_id"] = self._category_id_by_name(data["category"])
                if data.get("brand"):
                    data["brand_id"] = self.save_brand(data["brand"])
                product_id = self.db.scalar("SELECT id FROM products WHERE sku = ?",
                                            (data.get("sku"),))
                payload = {
                    "sku": data.get("sku") or self.generate_sku(),
                    "name": data.get("name") or data.get("sku"),
                    "barcode": data.get("barcode"),
                    "category_id": data.get("category_id"),
                    "brand_id": data.get("brand_id"),
                    "reference": data.get("reference"),
                    "unit": data.get("unit") or "u",
                    "purchase_price_cents": data.get("purchase_price", 0),
                    "sale_price_cents": data.get("sale_price", 0),
                    "vat_rate_bp": data.get("vat", 20),
                    "stock": data.get("stock", 0) if not product_id else 0,
                    "stock_min": data.get("stock_min", 0),
                    "stock_max": data.get("stock_max", 0),
                    "location": data.get("location"),
                    "description": data.get("description"),
                    "is_active": True,
                }
                if dry_run:
                    created += 1
                    continue
                if product_id:
                    self.save_product(payload, product_id=product_id, user_id=user_id)
                    updated += 1
                else:
                    self.save_product(payload, user_id=user_id)
                    created += 1
            except (ValidationError, ValueError, KeyError) as exc:
                errors += 1
                error_rows.append(f"ligne {index}: {exc}")
        return {"created": created, "updated": updated, "errors": errors,
                "error_rows": error_rows[:50]}

    def _category_id_by_name(self, name: str) -> int | None:
        name = clean_text(name, 80)
        category_id = self.db.scalar("SELECT id FROM categories WHERE name = ?", (name,))
        if category_id:
            return int(category_id)
        code = name.upper().replace(" ", "-")[:20]
        return self.save_category({"code": code, "name": name, "kind": "product"})

    def export_products(self, path: Path | str, term: str = "") -> Path:
        products, _ = self.products(term=term, limit=100000)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            from openpyxl import Workbook

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Produits"
            headers = ["SKU", "Code-barres", "D\u00e9signation", "Cat\u00e9gorie", "Marque",
                       "R\u00e9f\u00e9rence", "Unit\u00e9", "Prix achat HT", "Prix vente HT",
                       "TVA %", "Prix TTC", "Stock", "Stock min", "Stock max",
                       "Emplacement", "Fournisseur", "Actif"]
            sheet.append(headers)
            for product in products:
                sheet.append([
                    product["sku"], product.get("barcode") or "", product["name"],
                    product.get("category_name") or "", product.get("brand_name") or "",
                    product.get("reference") or "", product.get("unit") or "u",
                    float(cents_to_money(product["purchase_price_cents"])),
                    float(cents_to_money(product["sale_price_cents"])),
                    float(Decimal(product["vat_rate_bp"]) / 100),
                    float(self.price_ttc(product)),
                    float(Decimal(product["stock"]) / 1000),
                    float(Decimal(product["stock_min"]) / 1000),
                    float(Decimal(product["stock_max"]) / 1000),
                    product.get("location") or "", product.get("supplier_name") or "",
                    "Oui" if product["is_active"] else "Non",
                ])
            workbook.save(path)
        else:
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["sku", "barcode", "designation", "categorie", "marque",
                                 "reference", "unite", "prix_achat", "prix_vente", "tva",
                                 "prix_ttc", "stock", "stock_min", "stock_max", "emplacement",
                                 "fournisseur", "actif"])
                for product in products:
                    writer.writerow([
                        product["sku"], product.get("barcode") or "", product["name"],
                        product.get("category_name") or "", product.get("brand_name") or "",
                        product.get("reference") or "", product.get("unit") or "u",
                        cents_to_money(product["purchase_price_cents"]),
                        cents_to_money(product["sale_price_cents"]),
                        Decimal(product["vat_rate_bp"]) / 100,
                        self.price_ttc(product),
                        Decimal(product["stock"]) / 1000,
                        Decimal(product["stock_min"]) / 1000,
                        Decimal(product["stock_max"]) / 1000,
                        product.get("location") or "", product.get("supplier_name") or "",
                        1 if product["is_active"] else 0,
                    ])
        return path

    # ------------------------------------------------------------------
    # customers / suppliers
    # ------------------------------------------------------------------
    def parties(self, table: str, term: str = "", active_only: bool = True,
                limit: int = 1000) -> list[dict]:
        where = ["1=1"]
        params: list = []
        if active_only:
            where.append("is_active = 1")
        if term:
            like = f"%{term}%"
            where.append("(name LIKE ? OR code LIKE ? OR company LIKE ? OR phone LIKE ? "
                         "OR email LIKE ? OR city LIKE ? OR ice LIKE ?)")
            params += [like] * 7
        clause = " AND ".join(where)
        rows = self.db.query(f"SELECT * FROM {table} WHERE {clause} ORDER BY name LIMIT ?",
                             (*params, int(limit)))
        return [dict(r) for r in rows]

    def party(self, table: str, party_id: int) -> dict:
        return self.db.fetch(table, party_id)

    def validate_party(self, data: dict, table: str) -> dict:
        name = clean_text(data.get("name"), 150)
        if not name:
            raise ValidationError("name", "nom obligatoire")
        values = {
            "name": name,
            "address": clean_text(data.get("address"), 250),
            "city": clean_text(data.get("city"), 80),
            "zip": clean_text(data.get("zip"), 12),
            "country": clean_text(data.get("country"), 60) or "Maroc",
            "phone": validate_phone(data.get("phone", "")),
            "mobile": validate_phone(data.get("mobile", "")),
            "email": validate_email(data.get("email", "")),
            "ice": validate_ice(data.get("ice", "")),
            "if_number": clean_text(data.get("if_number"), 20),
            "rc": clean_text(data.get("rc"), 30),
            "payment_terms": clean_text(data.get("payment_terms"), 120),
            "notes": clean_text(data.get("notes"), 2000),
            "is_active": 1 if data.get("is_active", True) else 0,
        }
        if table == "customers":
            values.update({
                "company": clean_text(data.get("company"), 150),
                "customer_type": data.get("customer_type", "individual"),
                "patente": clean_text(data.get("patente"), 30),
                "cnss": clean_text(data.get("cnss"), 30),
                "credit_limit_cents": money_to_cents(
                    validate_positive_number(data.get("credit_limit_cents", 0), "credit_limit")),
            })
        else:
            values["contact_person"] = clean_text(data.get("contact_person"), 120)
        return values

    def save_party(self, table: str, data: dict, party_id: int | None = None,
                   user_id: int | None = None, audit=None) -> int:
        values = self.validate_party(data, table)
        prefix = "CLI" if table == "customers" else "FRS"
        code = clean_text(data.get("code"), 20)
        if not code:
            code = self.next_party_code(table, prefix)
        duplicate = self.db.scalar(f"SELECT id FROM {table} WHERE code = ? AND id <> ?",
                                   (code, party_id or 0))
        if duplicate:
            raise ValidationError("code", f"le code {code} existe d\u00e9j\u00e0")
        values["code"] = code
        if party_id:
            self.db.update(table, party_id, **values)
            if audit:
                audit(f"{table[:-1]}.update", entity_type=table[:-1], entity_id=party_id,
                      details=values["name"])
            return party_id
        party_id = self.db.insert(table, **values, created_by=user_id, status="active")
        if audit:
            audit(f"{table[:-1]}.create", entity_type=table[:-1], entity_id=party_id,
                  details=values["name"])
        return party_id

    def delete_party(self, table: str, party_id: int) -> bool:
        """Soft-delete; refuses when documents reference the party."""
        references = {
            "customers": ["invoices", "quotes", "orders", "sales", "delivery_notes"],
            "suppliers": ["purchases", "purchase_invoices"],
        }[table]
        for reference in references:
            column = "customer_id" if table == "customers" else "supplier_id"
            if self.db.scalar(f"SELECT COUNT(*) FROM {reference} WHERE {column} = ?",
                              (party_id,), default=0):
                self.db.update(table, party_id, is_active=0, status="inactive")
                return False
        self.db.delete(table, party_id)
        return True

    def next_party_code(self, table: str, prefix: str) -> str:
        highest = int(self.db.scalar(f"SELECT COUNT(*) FROM {table}", default=0))
        for row in self.db.query(f"SELECT code FROM {table} ORDER BY id DESC LIMIT 20"):
            tail = str(row["code"])[-4:]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{prefix}{highest + 1:04d}"

    # ------------------------------------------------------------------
    # services
    # ------------------------------------------------------------------
    def services(self, term: str = "", active_only: bool = True) -> list[dict]:
        sql = """SELECT s.*, c.name AS category_name FROM services s
                 LEFT JOIN categories c ON c.id = s.category_id WHERE 1=1"""
        params: list = []
        if active_only:
            sql += " AND s.is_active = 1"
        if term:
            sql += " AND (s.name LIKE ? OR s.code LIKE ?)"
            params += [f"%{term}%", f"%{term}%"]
        sql += " ORDER BY s.name"
        return [dict(r) for r in self.db.query(sql, params)]

    def save_service(self, data: dict, service_id: int | None = None,
                     user_id: int | None = None) -> int:
        name = clean_text(data.get("name"), 150)
        code = clean_text(data.get("code"), 30)
        if not name:
            raise ValidationError("name", "nom du service obligatoire")
        if not code:
            count = int(self.db.scalar("SELECT COUNT(*) FROM services", default=0))
            code = f"SVC-{count + 1:04d}"
        duplicate = self.db.scalar("SELECT id FROM services WHERE code = ? AND id <> ?",
                                   (code, service_id or 0))
        if duplicate:
            raise ValidationError("code", f"le code {code} existe d\u00e9j\u00e0")
        values = {
            "code": code, "name": name,
            "description": clean_text(data.get("description"), 1000),
            "category_id": data.get("category_id") or None,
            "unit": clean_text(data.get("unit"), 12) or "u",
            "cost_cents": money_to_cents(
                validate_positive_number(data.get("cost_cents", 0), "cost")),
            "price_cents": money_to_cents(
                validate_positive_number(data.get("price_cents", 0), "price")),
            "vat_rate_bp": rate_to_db(validate_percent(data.get("vat_rate_bp", 20), "vat")),
            "duration_minutes": int(data.get("duration_minutes") or 0),
            "is_active": 1 if data.get("is_active", True) else 0,
        }
        if service_id:
            self.db.update("services", service_id, **values)
            return service_id
        return self.db.insert("services", **values, created_by=user_id, status="active")

    def delete_service(self, service_id: int) -> None:
        used = self.db.scalar(
            "SELECT COUNT(*) FROM sale_items WHERE service_id = ?", (service_id,), default=0)
        if used:
            self.db.update("services", service_id, is_active=0, status="inactive")
        else:
            self.db.delete("services", service_id)

    # ------------------------------------------------------------------
    # attachments / images
    # ------------------------------------------------------------------
    def store_image(self, source: Path | str, destination_dir: Path | str,
                    prefix: str = "img") -> str:
        source = Path(source)
        if not source.exists():
            return ""
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".png"
        target = destination_dir / f"{prefix}-{datetime.now():%Y%m%d%H%M%S%f}{suffix}"
        shutil.copy2(source, target)
        return str(target)
