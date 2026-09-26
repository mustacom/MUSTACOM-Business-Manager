"""Service container.

A single :class:`Services` object owns the database and every business
service.  Screens receive it from the main window, which keeps wiring in one
place and makes the whole business layer testable without Qt.
"""

from __future__ import annotations

from pathlib import Path

from .config import build_paths
from .core.auth import AuthService
from .core.backup import BackupService
from .core.crud import CatalogService
from .core.documents import (CashService, CreditNoteService, DeliveryService,
                             ExpenseService, InvoiceService, OrderService, PaymentService,
                             PurchaseService, QuoteService, RepairService, RouteNoteService,
                             SupplierReturnService)
from .core.license import LicenseService
from .core.numbering import Numbering
from .core.parties import PartyService
from .core.sales import SalesService
from .core.stock import StockService
from .db.database import App, Database


class Services(App):
    """Database + every service, wired once."""

    def __init__(self, db: Database, paths=None):
        super().__init__(db)
        self.paths = paths or build_paths()
        self.paths.ensure()
        self.auth = AuthService(db)
        self.numbering = Numbering(db)
        self.catalog = CatalogService(db)
        self.stock = StockService(db)
        self.parties = PartyService(db)
        self.sales = SalesService(db, self.numbering, self.stock, self.parties)
        self.quotes = QuoteService(db, self.numbering, self.stock, self.parties)
        self.orders = OrderService(db, self.numbering, self.stock, self.parties)
        self.deliveries = DeliveryService(db, self.numbering, self.stock, self.parties)
        self.route_notes = RouteNoteService(db, self.numbering, self.stock, self.parties)
        self.invoices = InvoiceService(db, self.numbering, self.stock, self.parties)
        self.supplier_returns = SupplierReturnService(db, self.numbering, self.stock)
        self.credit_notes = CreditNoteService(db)
        self.purchases = PurchaseService(db, self.numbering, self.stock, self.parties)
        self.expenses = ExpenseService(db, self.numbering)
        self.payments = PaymentService(db, self.numbering, self.parties)
        self.cash = CashService(db, self.numbering)
        self.repairs = RepairService(db, self.numbering, self.stock)
        self.backup = BackupService(db, self.paths.backups, self.settings)
        self.license = LicenseService(db, self.settings)

    # ------------------------------------------------------------------
    def audit_log(self, action: str, **kwargs) -> None:
        """Convenience wrapper used by the screens."""
        self.log(action, **kwargs)

    def money_symbol(self) -> str:
        return self.settings.currency_symbol()

    def bootstrap(self) -> None:
        """First-run setup: roles, default settings, catalogue seeds."""
        self.auth.ensure_roles()
        self.settings.ensure_defaults()
        self.catalog.seed_defaults()

    @classmethod
    def create(cls, db_path: Path | str | None = None) -> "Services":
        from .db.database import open_database

        paths = build_paths()
        target = Path(db_path) if db_path else paths.db
        db = open_database(target)
        return cls(db, paths)
