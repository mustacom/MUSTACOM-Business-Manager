"""Sequential document numbering: PREFIX-YEAR-0001.

Sequences live in ``document_sequences`` and are incremented inside the
caller's transaction, so two operators validating a sale at the same instant
never receive the same number.
"""

from __future__ import annotations

from datetime import datetime

from ..config import DOCUMENT_PREFIXES
from ..db.database import Database


def _year(date: str | datetime | None) -> int:
    if isinstance(date, datetime):
        return date.year
    if isinstance(date, str) and len(date) >= 4:
        try:
            return int(date[:4])
        except ValueError:
            pass
    return datetime.now().year


class Numbering:
    def __init__(self, db: Database):
        self.db = db

    def prefix_for(self, doc_type: str) -> str:
        return DOCUMENT_PREFIXES.get(doc_type, doc_type[:3].upper())

    def next_number(self, doc_type: str, date: str | datetime | None = None,
                    width: int = 4) -> str:
        """Reserve and return the next number for a document type/year."""
        year = _year(date)
        prefix = self.db.scalar(
            "SELECT prefix FROM document_sequences WHERE doc_type=? AND year=?",
            (doc_type, year)) or self.prefix_for(doc_type)
        with self.db.transaction():
            counter = self.db.scalar(
                "SELECT counter FROM document_sequences WHERE doc_type=? AND year=?",
                (doc_type, year))
            if counter is None:
                counter = self._initial_counter(doc_type, year, prefix, width)
                self.db.insert("document_sequences", doc_type=doc_type, year=year,
                               counter=counter, prefix=prefix)
            else:
                counter = int(counter) + 1
                self.db.execute(
                    "UPDATE document_sequences SET counter=? WHERE doc_type=? AND year=?",
                    (counter, doc_type, year))
        return f"{prefix}-{year}-{counter:0{width}d}"

    def peek(self, doc_type: str, date: str | datetime | None = None, width: int = 4) -> str:
        """Preview the next number without consuming it."""
        year = _year(date)
        counter = self.db.scalar(
            "SELECT counter FROM document_sequences WHERE doc_type=? AND year=?",
            (doc_type, year))
        prefix = self.db.scalar(
            "SELECT prefix FROM document_sequences WHERE doc_type=? AND year=?",
            (doc_type, year)) or self.prefix_for(doc_type)
        if counter is None:
            counter = self._initial_counter(doc_type, year, prefix, width)
        else:
            counter = int(counter) + 1
        return f"{prefix}-{year}-{counter:0{width}d}"

    def _initial_counter(self, doc_type: str, year: int, prefix: str, width: int) -> int:
        """Continue from the highest existing number (handy after a restore)."""
        pattern = f"{prefix}-{year}-%"
        tables = {
            "devis": ("quotes", "number"), "sale": ("sales", "number"),
            "invoice": ("invoices", "number"), "credit_note": ("credit_notes", "number"),
            "bl": ("delivery_notes", "number"), "br": ("route_notes", "number"),
            "bc_client": ("orders", "number"), "bc_supplier": ("orders", "number"),
            "return_client": ("return_notes", "number"),
            "return_supplier": ("return_notes", "number"),
            "purchase": ("purchases", "number"), "purchase_receipt": ("purchase_receipts", "number"),
            "purchase_invoice": ("purchase_invoices", "number"),
            "payment_in": ("payments", "number"), "payment_out": ("payments", "number"),
            "expense": ("expenses", "number"), "repair": ("repairs", "number"),
            "inventory": ("inventories", "number"), "cash_session": ("cash_sessions", "number"),
        }
        entry = tables.get(doc_type)
        if not entry:
            return 1
        table, column = entry
        rows = self.db.query(f"SELECT {column} FROM {table} WHERE {column} LIKE ?", (pattern,))
        highest = 0
        for row in rows:
            tail = str(row[column]).rsplit("-", 1)[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return highest + 1

    def set_counter(self, doc_type: str, year: int, counter: int, prefix: str | None = None) -> None:
        existing = self.db.scalar(
            "SELECT id FROM document_sequences WHERE doc_type=? AND year=?", (doc_type, year))
        if existing:
            values: dict = {"counter": int(counter)}
            if prefix:
                values["prefix"] = prefix
            self.db.update("document_sequences", existing, **values)
        else:
            self.db.insert("document_sequences", doc_type=doc_type, year=year,
                           counter=int(counter), prefix=prefix or self.prefix_for(doc_type))

    def list_counters(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM document_sequences ORDER BY doc_type, year DESC")]
