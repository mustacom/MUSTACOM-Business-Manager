"""Authentication, sessions and role-based access control.

Role templates follow the specification:

* Administrateur  -> everything
* G\u00e9rant         -> everything except user administration and licensing
* Caissier        -> POS, customers, sales, receipts, payments
* Magasinier      -> products, stock, purchases, suppliers
* Technicien      -> repairs, customers (read), products (read)
* Comptable       -> invoices, payments, expenses, reports, customers, suppliers

Per-user overrides are stored in ``user_permissions`` and win over the role
template, which lets an administrator fine-tune a single account.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from ..config import ACTIONS, MODULES
from ..db.database import Database, now_iso
from .security import (ValidationError, clean_text, hash_password, needs_rehash,
                       validate_password, validate_username, verify_password)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

ALL_PERMISSIONS = {(module, action) for module in MODULES for action in ACTIONS}


def _grant(*modules: str) -> set[tuple[str, str]]:
    return {(m, a) for m in modules for a in ACTIONS}


def _grant_view_only(*modules: str) -> set[tuple[str, str]]:
    return {(m, "view") for m in modules}


ROLE_TEMPLATES: dict[str, set[tuple[str, str]]] = {
    "admin": ALL_PERMISSIONS.copy(),
    "manager": _grant(
        "dashboard", "pos", "cash", "quotes", "orders", "delivery_notes", "route_notes",
        "invoices", "credit_notes", "purchases", "products", "stock", "customers",
        "suppliers", "services", "repairs", "expenses", "payments", "reports", "barcode",
        "backup", "settings",
    ),
    "cashier": _grant("dashboard", "pos", "customers", "payments", "services")
    | _grant_view_only("invoices", "credit_notes", "cash", "products", "reports")
    | {("cash", "view"), ("cash", "create")},
    "stockkeeper": _grant("products", "stock", "purchases", "suppliers", "barcode")
    | _grant_view_only("dashboard", "reports", "services", "customers"),
    "technician": _grant("repairs")
    | _grant_view_only("dashboard", "customers", "products", "services", "stock"),
    "accountant": _grant("invoices", "credit_notes", "payments", "expenses", "reports",
                         "customers", "suppliers", "purchases", "cash")
    | _grant_view_only("dashboard", "products", "quotes", "orders", "repairs"),
}

ROLE_LABELS = {
    "admin": "Administrateur",
    "manager": "G\u00e9rant",
    "cashier": "Caissier",
    "stockkeeper": "Magasinier",
    "technician": "Technicien",
    "accountant": "Comptable",
}


@dataclass
class Session:
    """An authenticated application session."""

    token: str
    user_id: int
    username: str
    full_name: str
    role_code: str
    permissions: set[tuple[str, str]] = field(default_factory=set)
    started_at: str = field(default_factory=now_iso)
    last_activity: str = field(default_factory=now_iso)
    timeout_minutes: int = 0

    def touch(self) -> None:
        self.last_activity = now_iso()

    def is_expired(self) -> bool:
        if not self.timeout_minutes:
            return False
        try:
            started = datetime.fromisoformat(self.last_activity.replace(" ", "T"))
        except ValueError:
            return True
        return datetime.now() > started + timedelta(minutes=self.timeout_minutes)

    def has(self, module: str, action: str = "view") -> bool:
        if self.role_code == "admin":
            return True
        return (module, action) in self.permissions or (module, "*") in self.permissions


class AuthService:
    """User accounts, login flow and permission checks."""

    def __init__(self, db: Database):
        self.db = db

    # -- bootstrap ----------------------------------------------------------
    def ensure_roles(self) -> None:
        existing = {r["code"] for r in self.db.query("SELECT code FROM roles")}
        permissions = self._ensure_permissions()
        for code, template in ROLE_TEMPLATES.items():
            role_id = self.db.scalar("SELECT id FROM roles WHERE code = ?", (code,))
            if role_id is None:
                role_id = self.db.insert(
                    "roles", code=code, name=ROLE_LABELS.get(code, code.title()),
                    description=f"R\u00f4le {ROLE_LABELS.get(code, code).lower()}",
                    is_system=1)
            current = {r["permission_id"] for r in self.db.query(
                "SELECT permission_id FROM role_permissions WHERE role_id = ?", (role_id,))}
            wanted = {permissions[pair] for pair in template if pair in permissions}
            for permission_id in wanted - current:
                self.db.insert("role_permissions", role_id=role_id, permission_id=permission_id)
            for permission_id in current - wanted:
                self.db.execute("DELETE FROM role_permissions WHERE role_id=? AND permission_id=?",
                                (role_id, permission_id))

    def _ensure_permissions(self) -> dict[tuple[str, str], int]:
        mapping: dict[tuple[str, str], int] = {}
        for module, action in sorted(ALL_PERMISSIONS):
            permission_id = self.db.scalar(
                "SELECT id FROM permissions WHERE module=? AND action=?", (module, action))
            if permission_id is None:
                permission_id = self.db.insert("permissions", module=module, action=action)
            mapping[(module, action)] = permission_id
        return mapping

    def permission_catalog(self) -> dict[str, list[dict]]:
        rows = self.db.query("SELECT id, module, action FROM permissions ORDER BY module, action")
        catalog: dict[str, list[dict]] = {}
        for row in rows:
            catalog.setdefault(row["module"], []).append(
                {"id": row["id"], "action": row["action"]})
        return catalog

    # -- users --------------------------------------------------------------
    def count_users(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM users", default=0))

    def list_users(self, include_inactive: bool = True) -> list[dict]:
        sql = """SELECT u.id, u.username, u.full_name, u.email, u.phone, u.is_active,
                        u.last_login_at, u.must_change_password, u.created_at,
                        r.code AS role_code, r.name AS role_name
                 FROM users u LEFT JOIN roles r ON r.id = u.role_id"""
        if not include_inactive:
            sql += " WHERE u.is_active = 1"
        sql += " ORDER BY u.username"
        return [dict(r) for r in self.db.query(sql)]

    def get_user(self, user_id: int) -> dict:
        return self.db.fetch("users", user_id)

    def get_user_by_name(self, username: str) -> dict:
        row = self.db.query_one("SELECT * FROM users WHERE username = ?", (username,))
        return dict(row) if row else {}

    def username_exists(self, username: str) -> bool:
        return self.db.scalar("SELECT 1 FROM users WHERE username = ?", (username,)) is not None

    def role_id(self, code: str) -> int | None:
        return self.db.scalar("SELECT id FROM roles WHERE code = ?", (code,))

    def create_user(self, username: str, password: str, full_name: str, role_code: str = "cashier",
                    email: str = "", phone: str = "", created_by: int | None = None,
                    must_change_password: bool = False) -> int:
        username = validate_username(username)
        validate_password(password)
        if self.username_exists(username):
            raise ValidationError("username", "cet identifiant existe d\u00e9j\u00e0")
        role_id = self.role_id(role_code)
        if role_id is None:
            raise ValidationError("role", "r\u00f4le inconnu")
        return self.db.insert(
            "users", username=username, password_hash=hash_password(password),
            full_name=clean_text(full_name, 120), email=clean_text(email, 120),
            phone=clean_text(phone, 32), role_id=role_id, is_active=1,
            must_change_password=1 if must_change_password else 0,
            created_by=created_by, status="active")

    def update_user(self, user_id: int, *, full_name: str | None = None, email: str | None = None,
                    phone: str | None = None, role_code: str | None = None,
                    is_active: bool | None = None) -> None:
        values: dict = {}
        if full_name is not None:
            values["full_name"] = clean_text(full_name, 120)
        if email is not None:
            values["email"] = clean_text(email, 120)
        if phone is not None:
            values["phone"] = clean_text(phone, 32)
        if role_code is not None:
            role_id = self.role_id(role_code)
            if role_id is None:
                raise ValidationError("role", "r\u00f4le inconnu")
            values["role_id"] = role_id
        if is_active is not None:
            values["is_active"] = 1 if is_active else 0
        if values:
            self.db.update("users", user_id, **values)

    def set_password(self, user_id: int, password: str) -> None:
        validate_password(password)
        self.db.update("users", user_id, password_hash=hash_password(password),
                       must_change_password=0)

    def delete_user(self, user_id: int) -> None:
        self.db.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
        self.db.delete("users", user_id)

    # -- permissions --------------------------------------------------------
    def role_permissions(self, role_code: str) -> set[tuple[str, str]]:
        rows = self.db.query(
            """SELECT p.module, p.action FROM role_permissions rp
               JOIN permissions p ON p.id = rp.permission_id
               JOIN roles r ON r.id = rp.role_id
               WHERE r.code = ?""", (role_code,))
        return {(r["module"], r["action"]) for r in rows}

    def set_role_permissions(self, role_code: str, permissions: Iterable[tuple[str, str]]) -> None:
        if role_code == "admin":
            return  # administrator always keeps every right
        role_id = self.role_id(role_code)
        if role_id is None:
            raise ValidationError("role", "r\u00f4le inconnu")
        catalog = self._ensure_permissions()
        wanted = {catalog[pair] for pair in permissions if pair in catalog}
        with self.db.transaction():
            self.db.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            for permission_id in wanted:
                self.db.insert("role_permissions", role_id=role_id, permission_id=permission_id)

    def user_overrides(self, user_id: int) -> dict[tuple[str, str], bool]:
        rows = self.db.query(
            """SELECT p.module, p.action, up.granted FROM user_permissions up
               JOIN permissions p ON p.id = up.permission_id WHERE up.user_id = ?""", (user_id,))
        return {(r["module"], r["action"]): bool(r["granted"]) for r in rows}

    def set_user_override(self, user_id: int, module: str, action: str, granted: bool) -> None:
        catalog = self._ensure_permissions()
        permission_id = catalog.get((module, action))
        if permission_id is None:
            return
        self.db.execute(
            """INSERT INTO user_permissions (user_id, permission_id, granted) VALUES (?,?,?)
               ON CONFLICT(user_id, permission_id) DO UPDATE SET granted=excluded.granted""",
            (user_id, permission_id, 1 if granted else 0))

    def effective_permissions(self, user: dict) -> set[tuple[str, str]]:
        role_code = self.role_code_of(user)
        permissions = self.role_permissions(role_code)
        for pair, granted in self.user_overrides(user["id"]).items():
            if granted:
                permissions.add(pair)
            else:
                permissions.discard(pair)
        return permissions

    def role_code_of(self, user: dict) -> str:
        row = self.db.query_one(
            """SELECT r.code FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.id = ?""", (user["id"],))
        return row["code"] if row else ""

    # -- login --------------------------------------------------------------
    def login(self, username: str, password: str) -> Session:
        username = clean_text(username, 32)
        user = self.get_user_by_name(username)
        if not user:
            # spend comparable work to avoid user enumeration timing leaks
            verify_password(password, "$argon2id$v=19$m=19456,t=2,p=1$"
                                    "AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
            raise ValidationError("username", "identifiant ou mot de passe incorrect")

        if not user["is_active"]:
            raise ValidationError("username", "ce compte est d\u00e9sactiv\u00e9")

        locked_until = user.get("locked_until")
        if locked_until:
            # An unparsable timestamp must fail *closed*, never open.
            try:
                release_at = datetime.fromisoformat(locked_until.replace(" ", "T"))
            except ValueError:
                raise ValidationError("username", "compte temporairement verrouill\u00e9")
            if datetime.now() < release_at:
                remaining = max(1, int((release_at - datetime.now()).total_seconds() // 60) + 1)
                raise ValidationError("username",
                                      f"compte temporairement verrouill\u00e9, "
                                      f"r\u00e9essayez dans {remaining} minute(s)")

        if not verify_password(password, user["password_hash"]):
            attempts = int(user.get("failed_attempts", 0)) + 1
            values: dict = {"failed_attempts": attempts}
            if attempts >= MAX_FAILED_ATTEMPTS:
                values["locked_until"] = (datetime.now() + timedelta(
                    minutes=LOCKOUT_MINUTES)).replace(microsecond=0).isoformat(sep=" ")
                values["failed_attempts"] = 0
            self.db.update("users", user["id"], **values)
            remaining = MAX_FAILED_ATTEMPTS - attempts
            raise ValidationError("username",
                                  f"identifiant ou mot de passe incorrect"
                                  + (f" - {remaining} tentative(s) restante(s)"
                                     if remaining > 0 else " - compte verrouill\u00e9"))

        if needs_rehash(user["password_hash"]):
            self.db.update("users", user["id"], password_hash=hash_password(password))

        self.db.update("users", user["id"], failed_attempts=0, locked_until=None,
                       last_login_at=now_iso())

        role_code = self.role_code_of(user)
        permissions = self.effective_permissions(user)
        return Session(token=secrets.token_hex(32), user_id=user["id"],
                       username=user["username"], full_name=user.get("full_name") or user["username"],
                       role_code=role_code, permissions=permissions)

    def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        user = self.get_user(user_id)
        if not user:
            raise ValidationError("username", "utilisateur introuvable")
        if not verify_password(old_password, user["password_hash"]):
            raise ValidationError("old_password", "ancien mot de passe incorrect")
        if old_password == new_password:
            raise ValidationError("new_password", "le nouveau mot de passe doit \u00eatre diff\u00e9rent")
        self.set_password(user_id, new_password)

    def build_session(self, user: dict, timeout_minutes: int = 0) -> Session:
        return Session(token=secrets.token_hex(32), user_id=user["id"],
                       username=user["username"],
                       full_name=user.get("full_name") or user["username"],
                       role_code=self.role_code_of(user),
                       permissions=self.effective_permissions(user),
                       timeout_minutes=timeout_minutes)
