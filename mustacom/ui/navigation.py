"""Sidebar structure: modules, groups, icons and order.

Keeping the navigation in data (rather than hard-coded widget calls) means a
new module is added by writing its screen and appending one tuple here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr


@dataclass(frozen=True)
class NavItem:
    module: str
    label_key: str
    icon: str
    shortcut: str = ""

    @property
    def label(self) -> str:
        return tr(self.label_key)


@dataclass(frozen=True)
class NavGroup:
    label_key: str
    items: tuple[NavItem, ...]


NAVIGATION: tuple[NavGroup, ...] = (
    NavGroup("nav.group.sales", (
        NavItem("dashboard", "nav.dashboard", "dashboard", "Ctrl+1"),
        NavItem("pos", "nav.pos", "cart", "Ctrl+2"),
        NavItem("cash", "nav.cash", "cash", "Ctrl+3"),
    )),
    NavGroup("nav.group.documents", (
        NavItem("quotes", "nav.quotes", "doc", "Ctrl+4"),
        NavItem("orders", "nav.orders", "doc", "Ctrl+5"),
        NavItem("delivery_notes", "nav.delivery_notes", "truck"),
        NavItem("route_notes", "nav.route_notes", "truck"),
        NavItem("invoices", "nav.invoices", "doc", "Ctrl+6"),
        NavItem("credit_notes", "nav.credit_notes", "doc"),
    )),
    NavGroup("nav.group.stock", (
        NavItem("products", "nav.products", "box", "Ctrl+7"),
        NavItem("stock", "nav.stock", "box"),
        NavItem("purchases", "nav.purchases", "truck"),
        NavItem("barcode", "nav.barcode", "box"),
    )),
    NavGroup("nav.group.relations", (
        NavItem("customers", "nav.customers", "user", "Ctrl+8"),
        NavItem("suppliers", "nav.suppliers", "user"),
    )),
    NavGroup("nav.group.services", (
        NavItem("services", "nav.services", "wrench"),
        NavItem("repairs", "nav.repairs", "wrench"),
    )),
    NavGroup("nav.group.finance", (
        NavItem("payments", "nav.payments", "cash"),
        NavItem("expenses", "nav.expenses", "cash"),
        NavItem("reports", "nav.reports", "chart", "Ctrl+9"),
    )),
    NavGroup("nav.group.admin", (
        NavItem("users", "nav.users", "shield"),
        NavItem("backup", "nav.backup", "backup"),
        NavItem("license", "nav.license", "key"),
        NavItem("settings", "nav.settings", "gear"),
    )),
)


def all_modules() -> list[str]:
    return [item.module for group in NAVIGATION for item in group.items]


def module_label(module: str) -> str:
    for group in NAVIGATION:
        for item in group.items:
            if item.module == module:
                return item.label
    return module
