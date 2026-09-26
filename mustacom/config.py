"""Application-wide configuration, paths and constants for MUSTACOM Business Manager.

Nothing in this module imports Qt, so it is safe to use from tests, CLI tools
and the license key generator.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

APP_NAME = "MUSTACOM BUSINESS MANAGER"
APP_SHORT_NAME = "Mustacom Business Manager"
APP_ID = "mustacom-business-manager"
APP_VERSION = "1.0.0"
APP_BUILD = 1
APP_AUTHOR = "MUSTACOM"
APP_COPYRIGHT = "\u00a9 MUSTACOM - Tous droits r\u00e9serv\u00e9s"
APP_WEBSITE = "www.mustacom.com"
APP_SUPPORT_EMAIL = "mustacom.services@gmail.com"

DB_FILENAME = "mustacom.db"
DB_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Morocco defaults (all of these are *defaults only* - they are always
# overridable from the Settings screen and stored in the `settings` table).
# ---------------------------------------------------------------------------

DEFAULT_CURRENCY_CODE = "MAD"
DEFAULT_CURRENCY_SYMBOL = "DH"
DEFAULT_TIMEZONE = "Africa/Casablanca"
DEFAULT_LOCALE = "fr"
SUPPORTED_LANGUAGES = ("fr", "ar", "en")
DEFAULT_DATE_FORMAT = "dd/MM/yyyy"
DEFAULT_DATETIME_FORMAT = "dd/MM/yyyy HH:mm"
DEFAULT_VAT_RATE = 20.0  # %

# ---------------------------------------------------------------------------
# Default company profile (pre-filled, editable in Settings)
# ---------------------------------------------------------------------------

DEFAULT_COMPANY = {
    "company_name": "MUSTACOM",
    "company_legal_form": "",
    "company_activity": "Fourniture informatique et bureautique - "
    "Services d'impression et publicitaire - N\u00e9goce",
    "company_address": "002 Cit\u00e9 Mini\u00e8re (Tawzakt)",
    "company_zip": "45800",
    "company_city": "Tinghir",
    "company_country": "Maroc",
    "company_phone": "07 08 78 51 53",
    "company_email": "mustacom.services@gmail.com",
    "company_website": "www.mustacom.com",
    "company_ice": "",
    "company_if": "",
    "company_rc": "",
    "company_cnss": "",
    "company_patente": "",
    "company_capital": "",
    "company_bank_name": "",
    "company_bank_rib": "",
    "company_bank_swift": "",
    "company_logo_path": "",
    "company_stamp_path": "",
    "company_signature_path": "",
    "document_footer": "Merci de votre confiance - " + APP_NAME,
    "document_legal": "",
    "payment_conditions": "Paiement \u00e0 r\u00e9ception de facture",
}

# ---------------------------------------------------------------------------
# Document number prefixes  ->  PREFIX-YEAR-0001
# ---------------------------------------------------------------------------

DOCUMENT_PREFIXES = {
    "devis": "DEV",
    "bc_client": "BCC",
    "bc_supplier": "BCF",
    "bl": "BL",
    "br": "BR",
    "sale": "VTE",
    "invoice": "FAC",
    "invoice_proforma": "PRO",
    "credit_note": "AVR",
    "return_client": "BRC",
    "return_supplier": "BRF",
    "purchase": "ACH",
    "purchase_receipt": "REC",
    "purchase_invoice": "FAF",
    "payment_in": "ENC",
    "payment_out": "DEB",
    "expense": "DEP",
    "repair": "REP",
    "stock_entry": "ENT",
    "stock_exit": "SOR",
    "stock_adjustment": "AJU",
    "inventory": "INV",
    "cash_session": "CS",
    "delivery": "LIV",
}

# ---------------------------------------------------------------------------
# Business enums (kept as plain strings in the DB, no ORM)
# ---------------------------------------------------------------------------

PAYMENT_METHODS = ("cash", "card", "transfer", "check", "credit", "mixed", "other")

INVOICE_STATUS = ("paid", "partial", "unpaid", "cancelled")
ORDER_STATUS = ("draft", "confirmed", "in_progress", "partial", "delivered", "cancelled")
DEVIS_STATUS = ("draft", "sent", "accepted", "refused", "converted", "expired", "cancelled")
BL_STATUS = ("draft", "partial", "delivered", "cancelled")
BR_STATUS = ("draft", "validated", "cancelled")
RETURN_STATUS = ("draft", "validated", "cancelled")
RETURN_CONDITIONS = ("new", "good", "used", "damaged", "defective")
REPAIR_STATUS = (
    "received",
    "diagnosis",
    "repairing",
    "waiting_parts",
    "done",
    "delivered",
    "cancelled",
)
PURCHASE_STATUS = ("draft", "ordered", "partial", "received", "invoiced", "cancelled")
PURCHASE_INVOICE_STATUS = ("unpaid", "partial", "paid", "cancelled")
STOCK_MOVEMENT_TYPES = (
    "purchase",
    "sale",
    "return_client",
    "return_supplier",
    "adjustment",
    "transfer",
    "damage",
    "loss",
    "inventory",
    "initial",
    "repair_part",
    "cancelled",
)
CASH_MOVEMENT_TYPES = (
    "open",
    "sale",
    "expense",
    "payment_in",
    "payment_out",
    "refund",
    "close",
    "adjustment",
)
PAPER_SIZES = ("a4", "a5", "thermal80", "thermal58")
CASH_SESSION_STATUS = ("open", "closed")

DEFAULT_ROLES = (
    "admin",
    "manager",
    "cashier",
    "stockkeeper",
    "technician",
    "accountant",
)

# module -> human label key ; used by the permission matrix UI
MODULES = (
    "dashboard",
    "pos",
    "cash",
    "quotes",
    "orders",
    "delivery_notes",
    "route_notes",
    "invoices",
    "credit_notes",
    "purchases",
    "products",
    "stock",
    "customers",
    "suppliers",
    "services",
    "repairs",
    "expenses",
    "payments",
    "reports",
    "barcode",
    "users",
    "settings",
    "license",
    "backup",
)

ACTIONS = ("view", "create", "edit", "delete", "print", "export", "validate")

# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

LICENSE_TYPES = ("trial", "standard", "professional", "enterprise")
TRIAL_DAYS = 30
LICENSE_KEY_PREFIX = "MUST"
LICENSE_FILE_EXT = ".mustacomlic"
MACHINE_REQUEST_EXT = ".mustacomreq"
EXPIRY_WARNING_DAYS = 15

# Master secret used to sign license keys.
#
# SECURITY: for a real commercial release you MUST override this at build time
# (see build_exe.bat -> MUSTACOM_LICENSE_SECRET) so that the shipped binary
# carries your own secret instead of the public default below.
DEFAULT_LICENSE_SECRET = "MUSTACOM-DEFAULT-DEV-SECRET-CHANGE-ME-2026"

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

DEFAULT_BACKUP_KEEP = 30
DEFAULT_BACKUP_HOUR = 20
DEFAULT_BACKUP_MINUTE = 0

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def app_base_dir() -> Path:
    """Directory containing the executable (frozen) or the source tree."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Safe, per-user application data directory.

    Windows  -> %APPDATA%\\MUSTACOM\\BusinessManager
    macOS    -> ~/Library/Application Support/MUSTACOM/BusinessManager
    Linux    -> ~/.local/share/MUSTACOM/BusinessManager
    """
    override = os.environ.get("MUSTACOM_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "MUSTACOM" / "BusinessManager"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "MUSTACOM" / "BusinessManager"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "MUSTACOM" / "BusinessManager"


@dataclass
class AppPaths:
    """All writable locations used by the application."""

    data: Path
    db: Path
    backups: Path
    logs: Path
    exports: Path
    attachments: Path
    images: Path
    temp: Path

    def ensure(self) -> "AppPaths":
        for folder in (
            self.data,
            self.backups,
            self.logs,
            self.exports,
            self.attachments,
            self.images,
            self.temp,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def build_paths(data_root: Path | None = None) -> AppPaths:
    root = Path(data_root) if data_root else data_dir()
    return AppPaths(
        data=root,
        db=root / DB_FILENAME,
        backups=root / "backups",
        logs=root / "logs",
        exports=root / "exports",
        attachments=root / "attachments",
        images=root / "images",
        temp=root / "temp",
    )


PATHS = build_paths()


def license_secret() -> str:
    """Master signing secret (overridable at build time via environment)."""
    return os.environ.get("MUSTACOM_LICENSE_SECRET", DEFAULT_LICENSE_SECRET)
