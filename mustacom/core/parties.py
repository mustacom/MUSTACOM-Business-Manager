"""Customer and supplier ledgers.

``customers.balance_cents`` is a *cache*: positive = the customer owes us.
The authoritative figure is recomputed from unpaid invoices minus payments
minus credit notes, so the cache can always be rebuilt with
:meth:`PartyService.recompute_customer`.
"""

from __future__ import annotations

from ..db.database import Database, now_iso
from .money import cents_to_money


class PartyService:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # customers
    # ------------------------------------------------------------------
    def customer_outstanding(self, customer_id: int) -> int:
        """Unpaid invoice total minus payments minus credit notes (centimes)."""
        if not customer_id:
            return 0
        invoices = int(self.db.scalar(
            """SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM invoices
               WHERE customer_id = ? AND invoice_type <> 'proforma'
                 AND status IN ('unpaid','partial')""", (customer_id,), default=0))
        payments = int(self.db.scalar(
            """SELECT COALESCE(SUM(amount_cents),0) FROM payments
               WHERE direction='in' AND party_type='customer' AND party_id = ?
                 AND status='validated'""", (customer_id,), default=0))
        credits = int(self.db.scalar(
            "SELECT COALESCE(SUM(total_cents),0) FROM credit_notes WHERE customer_id = ?",
            (customer_id,), default=0))
        return invoices - payments - credits

    def recompute_customer(self, customer_id: int) -> int:
        balance = self.customer_outstanding(customer_id)
        self.db.update("customers", customer_id, balance_cents=balance)
        return balance

    def adjust_customer_balance(self, customer_id: int, delta_cents: int) -> int:
        if not customer_id or not delta_cents:
            return self.customer_balance(customer_id)
        self.db.execute("UPDATE customers SET balance_cents = balance_cents + ?, updated_at = ? "
                        "WHERE id = ?", (int(delta_cents), now_iso(), customer_id))
        return self.customer_balance(customer_id)

    def customer_balance(self, customer_id: int) -> int:
        return int(self.db.scalar("SELECT balance_cents FROM customers WHERE id = ?",
                                  (customer_id,), default=0))

    def customer_credit_available(self, customer_id: int) -> int:
        row = self.db.query_one(
            "SELECT credit_limit_cents, balance_cents FROM customers WHERE id = ?",
            (customer_id,))
        if not row:
            return 0
        limit = int(row["credit_limit_cents"] or 0)
        if limit <= 0:
            return 0
        return max(0, limit - int(row["balance_cents"] or 0))

    def customer_statement(self, customer_id: int, date_from: str = "",
                           date_to: str = "") -> list[dict]:
        entries: list[dict] = []
        invoices = self.db.query(
            """SELECT id, number, date, total_cents, paid_cents, status, invoice_type
               FROM invoices WHERE customer_id = ?
                 AND invoice_type <> 'proforma' AND status <> 'cancelled'""", (customer_id,))
        for row in invoices:
            entries.append({
                "date": row["date"], "type": "invoice", "number": row["number"],
                "label": f"Facture {row['number']}", "id": row["id"],
                "debit_cents": int(row["total_cents"]),
                "credit_cents": int(row["paid_cents"]),
                "balance_cents": int(row["total_cents"]) - int(row["paid_cents"]),
                "status": row["status"],
            })
        payments = self.db.query(
            """SELECT id, number, date, amount_cents, method FROM payments
               WHERE direction='in' AND party_type='customer' AND party_id = ?
                 AND status='validated'""", (customer_id,))
        for row in payments:
            entries.append({
                "date": row["date"], "type": "payment", "number": row["number"],
                "label": f"Paiement {row['number']} ({row['method']})", "id": row["id"],
                "debit_cents": 0, "credit_cents": int(row["amount_cents"]),
                "balance_cents": -int(row["amount_cents"]), "status": "validated",
            })
        credits = self.db.query(
            "SELECT id, number, date, total_cents FROM credit_notes WHERE customer_id = ?",
            (customer_id,))
        for row in credits:
            entries.append({
                "date": row["date"], "type": "credit_note", "number": row["number"],
                "label": f"Avoir {row['number']}", "id": row["id"],
                "debit_cents": 0, "credit_cents": int(row["total_cents"]),
                "balance_cents": -int(row["total_cents"]), "status": "validated",
            })
        sales = self.db.query(
            """SELECT id, number, date, total_cents, payment_method FROM sales
               WHERE customer_id = ? AND status='validated' AND is_return = 0""",
            (customer_id,))
        for row in sales:
            entries.append({
                "date": row["date"], "type": "sale", "number": row["number"],
                "label": f"Vente {row['number']} ({row['payment_method']})", "id": row["id"],
                "debit_cents": int(row["total_cents"]), "credit_cents": 0,
                "balance_cents": 0, "status": "validated",
            })

        if date_from:
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to + " 23:59:59"]
        entries.sort(key=lambda item: (item["date"], item["number"]))

        running = 0
        for entry in entries:
            if entry["type"] == "sale":
                continue  # POS cash sales do not feed the account balance
            running += entry["balance_cents"]
            entry["running_cents"] = running
        return entries

    def balances(self, only_debtors: bool = True) -> list[dict]:
        sql = """SELECT c.id, c.code, c.name, c.company, c.phone, c.credit_limit_cents,
                        c.balance_cents,
                        (SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM invoices i
                          WHERE i.customer_id = c.id AND i.status IN ('unpaid','partial')
                            AND i.invoice_type <> 'proforma') AS outstanding_cents
                 FROM customers c WHERE c.is_active = 1"""
        if only_debtors:
            sql += " AND c.balance_cents > 0"
        sql += " ORDER BY c.balance_cents DESC, c.name"
        return [dict(r) for r in self.db.query(sql)]

    # ------------------------------------------------------------------
    # suppliers
    # ------------------------------------------------------------------
    def supplier_outstanding(self, supplier_id: int) -> int:
        if not supplier_id:
            return 0
        invoices = int(self.db.scalar(
            """SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM purchase_invoices
               WHERE supplier_id = ? AND status IN ('unpaid','partial')""",
            (supplier_id,), default=0))
        payments = int(self.db.scalar(
            """SELECT COALESCE(SUM(amount_cents),0) FROM payments
               WHERE direction='out' AND party_type='supplier' AND party_id = ?
                 AND status='validated'""", (supplier_id,), default=0))
        return invoices - payments

    def recompute_supplier(self, supplier_id: int) -> int:
        balance = self.supplier_outstanding(supplier_id)
        self.db.update("suppliers", supplier_id, balance_cents=balance)
        return balance

    def adjust_supplier_balance(self, supplier_id: int, delta_cents: int) -> int:
        if not supplier_id or not delta_cents:
            return self.supplier_balance(supplier_id)
        self.db.execute("UPDATE suppliers SET balance_cents = balance_cents + ?, updated_at = ? "
                        "WHERE id = ?", (int(delta_cents), now_iso(), supplier_id))
        return self.supplier_balance(supplier_id)

    def supplier_balance(self, supplier_id: int) -> int:
        return int(self.db.scalar("SELECT balance_cents FROM suppliers WHERE id = ?",
                                  (supplier_id,), default=0))

    def supplier_statement(self, supplier_id: int, date_from: str = "",
                           date_to: str = "") -> list[dict]:
        entries: list[dict] = []
        invoices = self.db.query(
            """SELECT id, number, date, total_cents, paid_cents, status FROM purchase_invoices
               WHERE supplier_id = ? AND status <> 'cancelled'""", (supplier_id,))
        for row in invoices:
            entries.append({
                "date": row["date"], "type": "invoice", "number": row["number"],
                "label": f"Facture fournisseur {row['number']}", "id": row["id"],
                "debit_cents": 0, "credit_cents": int(row["total_cents"]),
                "balance_cents": int(row["total_cents"]) - int(row["paid_cents"]),
                "status": row["status"],
            })
        payments = self.db.query(
            """SELECT id, number, date, amount_cents, method FROM payments
               WHERE direction='out' AND party_type='supplier' AND party_id = ?
                 AND status='validated'""", (supplier_id,))
        for row in payments:
            entries.append({
                "date": row["date"], "type": "payment", "number": row["number"],
                "label": f"Paiement {row['number']} ({row['method']})", "id": row["id"],
                "debit_cents": int(row["amount_cents"]), "credit_cents": 0,
                "balance_cents": -int(row["amount_cents"]), "status": "validated",
            })
        if date_from:
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to + " 23:59:59"]
        entries.sort(key=lambda item: (item["date"], item["number"]))
        running = 0
        for entry in entries:
            running += entry["balance_cents"]
            entry["running_cents"] = running
        return entries

    def supplier_balances(self, only_creditors: bool = True) -> list[dict]:
        sql = """SELECT s.id, s.code, s.name, s.contact_person, s.phone, s.payment_terms,
                        s.balance_cents,
                        (SELECT COALESCE(SUM(total_cents - paid_cents),0) FROM purchase_invoices pi
                          WHERE pi.supplier_id = s.id AND pi.status IN ('unpaid','partial'))
                          AS outstanding_cents
                 FROM suppliers s WHERE s.is_active = 1"""
        if only_creditors:
            sql += " AND s.balance_cents > 0"
        sql += " ORDER BY s.balance_cents DESC, s.name"
        return [dict(r) for r in self.db.query(sql)]

    # ------------------------------------------------------------------
    def next_code(self, table: str, prefix: str) -> str:
        rows = self.db.query(f"SELECT code FROM {table} ORDER BY id DESC LIMIT 1")
        highest = 0
        for row in rows:
            tail = str(row["code"])[-4:]
            if tail.isdigit():
                highest = int(tail)
        highest = max(highest, int(self.db.scalar(
            f"SELECT COUNT(*) FROM {table}", default=0)))
        return f"{prefix}{highest + 1:04d}"

    def money(self, cents: int):
        return cents_to_money(cents)
