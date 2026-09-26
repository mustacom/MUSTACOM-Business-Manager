"""Realistic demonstration dataset for training and evaluation.

Idempotent: it only inserts when the tables are still empty, so calling it on
a production database that already holds data does nothing.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..db.database import now_iso

# sku, name, category, brand, unit, purchase, sale, vat, stock, min, barcode
PRODUCTS = [
    ("PRD-00001", "Papier A4 80g - ramette 500 feuilles", "PAPETERIE", "Double A", "u",
     42.00, 55.00, 20, 240, 40, "6111234500017"),
    ("PRD-00002", "Stylo bille bleu BIC Cristal", "BUREAU", "BIC", "u",
     1.20, 2.50, 20, 800, 100, "6111234500024"),
    ("PRD-00003", "Cahier 96 pages grands carreaux", "SCOLAIRE", "Atlas", "u",
     3.50, 6.00, 20, 320, 50, "6111234500031"),
    ("PRD-00004", "Agrafeuse m\u00e9tallique N\u00b024", "BUREAU", "Kangaro", "u",
     18.00, 32.00, 20, 45, 10, "6111234500048"),
    ("PRD-00005", "Cl\u00e9 USB 32 Go USB 3.0", "INFORMATIQUE", "SanDisk", "u",
     65.00, 110.00, 20, 60, 10, "6111234500055"),
    ("PRD-00006", "Souris sans fil 2.4 GHz", "INFORMATIQUE", "Logitech", "u",
     75.00, 135.00, 20, 38, 8, "6111234500062"),
    ("PRD-00007", "Clavier filaire AZERTY", "INFORMATIQUE", "HP", "u",
     85.00, 149.00, 20, 26, 6, "6111234500079"),
    ("PRD-00008", "C\u00e2ble HDMI 2.0 - 2 m\u00e8tres", "ACCESSOIRES", "Generic", "u",
     22.00, 45.00, 20, 70, 15, "6111234500086"),
    ("PRD-00009", "Toner HP 85A noir (CE285A)", "CARTOUCHES", "HP", "u",
     320.00, 520.00, 20, 18, 5, "6111234500093"),
    ("PRD-00010", "Cartouche d'encre Epson 664 noire", "CARTOUCHES", "Epson", "u",
     85.00, 145.00, 20, 22, 6, "6111234500109"),
    ("PRD-00011", "Cartable scolaire 2 compartiments", "SCOLAIRE", "Atlas", "u",
     95.00, 175.00, 20, 30, 8, "6111234500116"),
    ("PRD-00012", "Classeur A4 levier 80 mm", "BUREAU", "Esselte", "u",
     12.00, 24.00, 20, 90, 20, "6111234500123"),
    ("PRD-00013", "Livre : Apprendre l'informatique", "LIBRAIRIE", "", "u",
     60.00, 95.00, 10, 25, 5, "6111234500130"),
    ("PRD-00014", "\u00c9cran LED 24\" Full HD", "INFORMATIQUE", "Samsung", "u",
     950.00, 1450.00, 20, 12, 3, "6111234500147"),
    ("PRD-00015", "Souris filaire optique", "ACCESSOIRES", "HP", "u",
     25.00, 49.00, 20, 0, 10, "6111234500154"),
    ("PRD-00016", "Ramette papier A3 80g", "PAPETERIE", "Double A", "u",
     88.00, 135.00, 20, 4, 6, "6111234500161"),
    ("PRD-00017", "C\u00e2ble r\u00e9seau RJ45 Cat6 - 3 m", "ACCESSOIRES", "Generic", "u",
     12.00, 28.00, 20, 120, 20, "6111234500178"),
    ("PRD-00018", "Disque dur externe 1 To", "INFORMATIQUE", "WD", "u",
     420.00, 690.00, 20, 9, 3, "6111234500185"),
    ("PRD-00019", "Calculatrice scientifique CASIO", "SCOLAIRE", "Casio", "u",
     120.00, 210.00, 20, 20, 5, "6111234500192"),
    ("PRD-00020", "Rame papier photo A4 brillant", "IMPRESSION", "Epson", "u",
     55.00, 99.00, 20, 35, 8, "6111234500208"),
]

SUPPLIERS = [
    ("FRS0001", "Bureau Plus Casablanca", "M. Karim Alaoui", "Zone industrielle Sidi Ghanem",
     "Casablanca", "0522 33 44 55", "bureau.plus@exemple.ma", "001123456000011"),
    ("FRS0002", "Informatique Atlas SARL", "Mme Nadia Bennani", "Avenue Hassan II",
     "Marrakech", "0524 55 66 77", "contact@atlas-info.ma", "001123456000028"),
    ("FRS0003", "Papeterie du Sud", "M. Youssef Idrissi", "Quartier industriel",
     "Agadir", "0528 77 88 99", "info@papeterie-sud.ma", "001123456000035"),
]

CUSTOMERS = [
    ("CLI0001", "Client comptoir", "", "individual", "", "Tinghir", "07 08 78 51 53",
     "", "", "", "", 0),
    ("CLI0002", "Soci\u00e9t\u00e9 Mini\u00e8re de Tawzakt", "Soci\u00e9t\u00e9 Mini\u00e8re de Tawzakt",
     "company", "Cit\u00e9 Mini\u00e8re", "Tinghir", "0524 82 10 20",
     "compta@miniere-tawzakt.ma", "001987654000047", "12345678", "45678", 100_000.00),
    ("CLI0003", "Association Atlas pour le D\u00e9veloppement", "Association Atlas",
     "association", "Rue Mohammed V", "Tinghir", "0661 22 33 44",
     "atlas.dev@exemple.ma", "002345678000053", "23456789", "56789", 20_000.00),
    ("CLI0004", "Lyc\u00e9e Al Massira", "\u00c9tablissement scolaire", "school",
     "Avenue des FAR", "Tinghir", "0524 83 40 50", "direction@lycee-massira.ma",
     "003456789000060", "34567890", "67890", 50_000.00),
    ("CLI0005", "Commune de Tinghir", "Administration", "public", "Place centrale",
     "Tinghir", "0524 82 00 00", "", "00456789000076", "45678901", "78901", 0),
]

EXPENSE_CATEGORIES = [
    ("EXP-LOYER", "Loyer"),
    ("EXP-ELEC", "\u00c9lectricit\u00e9"),
    ("EXP-INTERNET", "Internet"),
    ("EXP-TRANSPORT", "Transport"),
    ("EXP-PUB", "Publicit\u00e9"),
]


def seed_demo_data(services, *, with_sales: bool = True, seed: int = 2026) -> int:
    """Insert the demonstration dataset.  Returns the number of products."""
    db = services.db
    if int(db.scalar("SELECT COUNT(*) FROM products", default=0)) > 0:
        return 0

    rng = random.Random(seed)
    today = date.today()
    year = today.year

    with db.transaction():
        # suppliers
        supplier_ids: dict[str, int] = {}
        for code, name, contact, address, city, phone, email, ice in SUPPLIERS:
            supplier_ids[code] = db.insert(
                "suppliers", code=code, name=name, contact_person=contact, address=address,
                city=city, phone=phone, email=email, ice=ice, payment_terms="30 jours",
                is_active=1, status="active")

        # customers
        customer_ids: dict[str, int] = {}
        for (code, name, company, kind, address, city, phone, email, ice, if_number,
             rc, credit) in CUSTOMERS:
            customer_ids[code] = db.insert(
                "customers", code=code, name=name, company=company, customer_type=kind,
                address=address, city=city, phone=phone, email=email, ice=ice,
                if_number=if_number, rc=rc, credit_limit_cents=int(credit * 100),
                country="Maroc", is_active=1, status="active")

        # categories for expenses
        expense_ids: dict[str, int] = {}
        for code, name in EXPENSE_CATEGORIES:
            existing = db.scalar("SELECT id FROM categories WHERE code = ?", (code,))
            expense_ids[code] = existing or db.insert(
                "categories", code=code, name=name, kind="expense", is_active=1,
                status="active")

        # products
        product_ids: dict[str, int] = {}
        for (sku, name, category, brand, unit, purchase, sale, vat, stock, minimum,
             barcode) in PRODUCTS:
            category_id = db.scalar("SELECT id FROM categories WHERE code = ?", (category,))
            brand_id = None
            if brand:
                brand_id = services.catalog.save_brand(brand)
            product_id = services.catalog.save_product({
                "sku": sku, "barcode": barcode, "name": name,
                "category_id": category_id, "brand_id": brand_id,
                "reference": sku.replace("PRD-", "REF-"), "unit": unit,
                "purchase_price_cents": purchase, "sale_price_cents": sale,
                "vat_rate_bp": vat, "stock": stock, "stock_min": minimum,
                "stock_max": maximum_of(stock), "location": f"\u00c9tag\u00e8re {sku[-2:]}",
                "supplier_id": supplier_ids.get("FRS0001"),
                "description": f"{name} - fournisseur {category.lower()}",
            })
            product_ids[sku] = product_id

        # vehicles / drivers
        driver_id = db.insert("drivers", name="Hammou A\u00eft Ali", phone="0661 11 22 33",
                              license_number="T-456789", is_active=1, status="active")
        vehicle_id = db.insert("vehicles", name="Renault Kangoo", registration="12345-A-45",
                               capacity="800 kg", is_active=1, status="active")

        if not with_sales:
            return len(product_ids)

        # cash session
        session_id = services.cash.open_session(2000 * 100, user_id=1)["id"]

        # historical sales over the last 45 days
        product_rows = [services.catalog.product(pid) for pid in product_ids.values()]
        for offset in range(45, -1, -1):
            day = today - timedelta(days=offset)
            if day.weekday() == 6:                # Sunday: closed
                continue
            for _ in range(rng.randint(2, 7)):
                lines = []
                for _ in range(rng.randint(1, 4)):
                    row = rng.choice(product_rows)
                    if row["stock"] <= 0:
                        continue
                    lines.append(SaleLine(row, rng.randint(1, 4)))
                if not lines:
                    continue
                customer_id = None
                method = rng.choices(["cash", "card", "credit", "check"],
                                     [70, 15, 10, 5])[0]
                if method in ("credit", "check"):
                    customer_id = rng.choice([customer_ids["CLI0002"],
                                              customer_ids["CLI0003"],
                                              customer_ids["CLI0004"]])
                stamp = f"{day.isoformat()} {rng.randint(9, 18):02d}:" \
                        f"{rng.randint(0, 59):02d}:00"
                try:
                    services.sales.validate_sale(
                        [line.item for line in lines],
                        customer_id=customer_id, payment_method=method,
                        cash_session_id=session_id, user_id=1,
                        timestamp=stamp)
                except Exception:
                    continue

        # expenses
        for offset in (5, 12, 20, 27):
            day = (today - timedelta(days=offset)).isoformat()
            category, amount = rng.choice([
                (expense_ids["EXP-LOYER"], 3500.00),
                (expense_ids["EXP-ELEC"], 420.00),
                (expense_ids["EXP-INTERNET"], 350.00),
                (expense_ids["EXP-TRANSPORT"], 250.00),
                (expense_ids["EXP-PUB"], 800.00),
            ])
            services.expenses.save(date=day, category_id=category,
                                   description="D\u00e9pense de fonctionnement",
                                   amount_cents=int(amount * 100), method="cash",
                                   cash_session_id=session_id, user_id=1)

        # purchases
        from .sales import CartItem as _CartItem
        purchase = services.purchases.save(
            [_CartItem.from_product(p, 5) for p in product_rows[:8]],
            supplier_id=supplier_ids["FRS0002"],
            supplier_ref="CMD-2026-118", user_id=1)
        services.purchases.receive(purchase["id"],
                                   {i["id"]: 20 for i in purchase["items"]},
                                   user_id=1)

        # a repair ticket
        services.repairs.save(
            customer_id=customer_ids["CLI0002"], device_type="laptop",
            device_brand="HP", device_model="ProBook 450", serial_number="CND1234XYZ",
            problem="\u00c9cran qui clignote et batterie faible",
            diagnosis="C\u00e2ble d'\u00e9cran endommag\u00e9, batterie \u00e0 remplacer",
            labor_cents=15000, parts=[{"label": "Batterie HP ProBook",
                                      "quantity": 1, "unit_price_cents": 45000}],
            deposit_cents=20000, technician_id=1, eta=(today + timedelta(days=2)).isoformat(),
            status="repairing", user_id=1)

        # a quotation
        services.quotes.save(
            [_CartItem.from_product(product_rows[0], 20),
             _CartItem.from_product(product_rows[8], 2)],
            customer_id=customer_ids["CLI0004"], notes="Offre valable 30 jours",
            terms="Paiement \u00e0 30 jours", user_id=1)

        for party_id in list(customer_ids.values()):
            services.parties.recompute_customer(party_id)
        for party_id in list(supplier_ids.values()):
            services.parties.recompute_supplier(party_id)

    return len(product_ids)


def maximum_of(stock: int) -> int:
    return max(stock * 3, 50)


class SaleLine:
    """Adapter turning a product row into a CartItem."""

    def __init__(self, product: dict, qty: int):
        from .sales import CartItem

        self.item = CartItem.from_product(product, qty)
