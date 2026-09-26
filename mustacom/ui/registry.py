"""Module -> screen factory registry.

Imported lazily by :class:`MainWindow` so that a broken module can never stop
the application from starting: :func:`resolve` catches import errors and
substitutes a diagnostic placeholder screen.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QLabel, QWidget

from ..i18n import tr
from .screens.base import BaseScreen
from .screens.dashboard import DashboardScreen


class PlaceholderScreen(BaseScreen):
    """Shown when a module failed to import, with the real error message."""

    def __init__(self, services, window, module: str = "", detail: str = ""):
        self.module = module
        super().__init__(services, window)
        self._detail = detail

    def build(self) -> None:
        layout = self.root
        title = QLabel(f"Module indisponible : {self.module}")
        title.setObjectName("ErrorLabel")
        detail = QLabel(self._detail or tr("msg.not_implemented"))
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addStretch(1)
        super().build()


def _lazy(module_path: str, class_name: str, fallback_module: str = "") -> Callable:
    def factory(services, window):
        try:
            from importlib import import_module

            screen_module = import_module(
                "mustacom.ui." + module_path.lstrip("."))
            return getattr(screen_module, class_name)(services, window)
        except Exception as exc:            # pragma: no cover - defensive
            import traceback

            traceback.print_exc()
            return PlaceholderScreen(services, window,
                                     fallback_module or module_path.rsplit(".", 1)[-1],
                                     f"{type(exc).__name__}: {exc}")

    return factory


SCREENS: dict[str, Callable] = {
    "dashboard": DashboardScreen,
    "pos": _lazy(".screens.pos", "PosScreen", "pos"),
    "cash": _lazy(".screens.cash", "CashScreen", "cash"),
    "quotes": _lazy(".screens.quotes", "QuotesScreen", "quotes"),
    "orders": _lazy(".screens.orders", "OrdersScreen", "orders"),
    "delivery_notes": _lazy(".screens.delivery_notes", "DeliveryNotesScreen",
                            "delivery_notes"),
    "route_notes": _lazy(".screens.route_notes", "RouteNotesScreen", "route_notes"),
    "invoices": _lazy(".screens.invoices", "InvoicesScreen", "invoices"),
    "credit_notes": _lazy(".screens.credit_notes", "CreditNotesScreen", "credit_notes"),
    "purchases": _lazy(".screens.purchases", "PurchasesScreen", "purchases"),
    "products": _lazy(".screens.products", "ProductsScreen", "products"),
    "stock": _lazy(".screens.stock", "StockScreen", "stock"),
    "customers": _lazy(".screens.customers", "CustomersScreen", "customers"),
    "suppliers": _lazy(".screens.suppliers", "SuppliersScreen", "suppliers"),
    "services": _lazy(".screens.services", "ServicesScreen", "services"),
    "repairs": _lazy(".screens.repairs", "RepairsScreen", "repairs"),
    "expenses": _lazy(".screens.expenses", "ExpensesScreen", "expenses"),
    "payments": _lazy(".screens.payments", "PaymentsScreen", "payments"),
    "reports": _lazy(".screens.reports", "ReportsScreen", "reports"),
    "barcode": _lazy(".screens.barcode", "BarcodeScreen", "barcode"),
    "users": _lazy(".screens.users", "UsersScreen", "users"),
    "settings": _lazy(".screens.settings", "SettingsScreen", "settings"),
    "license": _lazy(".screens.license", "LicenseScreen", "license"),
    "backup": _lazy(".screens.backup", "BackupScreen", "backup"),
}
