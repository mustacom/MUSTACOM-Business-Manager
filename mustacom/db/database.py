"""Database layer: connection management, migrations, settings store, audit log.

Design notes
------------
* One ``sqlite3`` connection per thread (``threading.local``) so the Qt UI
  thread and any worker threads never share a cursor.
* WAL journal mode + ``synchronous=NORMAL`` gives good concurrency for a
  single-machine POS while staying crash-safe.
* All SQL in the application uses parameter binding, never string
  interpolation, which removes the SQL-injection class of bugs.
* Money/quantity columns are integers (see :mod:`mustacom.core.money`).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from ..config import APP_VERSION, DB_SCHEMA_VERSION, DEFAULT_COMPANY

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_local = threading.local()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """Local naive ISO timestamp, second precision (Morocco local time)."""
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today_iso() -> str:
    return datetime.now().date().isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class Database:
    """Thin, explicit data-access layer over SQLite."""

    def __init__(self, path: Path | str, echo_sql: bool = False):
        self.path = Path(path)
        self.echo_sql = echo_sql
        self._lock = threading.RLock()
        self._migrating = False
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- connections --------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(_local, "connections", {}).get(str(self.path))
        if conn is None:
            conn = self._create_connection()
            _local.connections = getattr(_local, "connections", {})
            _local.connections[str(self.path)] = conn
        return conn

    def _create_connection(self) -> sqlite3.Connection:
        uri = f"file:{self.path}?mode=rwc"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0, isolation_level=None,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -16000")
        return conn

    def close(self) -> None:
        conn = getattr(_local, "connections", {}).pop(str(self.path), None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    def close_all(self) -> None:
        for conn in list(getattr(_local, "connections", {}).values()):
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _local.connections = {}

    # -- primitives ---------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        if self.echo_sql:
            print("[SQL]", sql, params)
        return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
        return self.conn.executemany(sql, [tuple(p) for p in seq])

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = (), default=None):
        row = self.query_one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    def table_columns(self, table: str) -> set[str]:
        """Column names of a table (cached per connection)."""
        cache = getattr(_local, "col_cache", None)
        if cache is None:
            cache = {}
            _local.col_cache = cache
        key = f"{self.path}::{table}"
        if key not in cache:
            cache[key] = {row["name"] for row in self.query(f"PRAGMA table_info({table})")}
        return cache[key]

    def insert(self, table: str, **values) -> int:
        """Insert a row, auto-filling the audit columns the table actually has."""
        columns = self.table_columns(table)
        if "created_at" in columns:
            values.setdefault("created_at", now_iso())
        if "updated_at" in columns:
            values.setdefault("updated_at", now_iso())
        if "status" in columns:
            values.setdefault("status", "active")
        unknown = set(values) - columns
        if unknown:
            raise KeyError(f"{table}: unknown column(s) {sorted(unknown)}")
        names = ", ".join(values.keys())
        marks = ", ".join("?" for _ in values)
        cur = self.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})",
                           tuple(values.values()))
        return int(cur.lastrowid)

    def update(self, table: str, row_id: int, **values) -> int:
        if not values:
            return 0
        columns = self.table_columns(table)
        unknown = set(values) - columns
        if unknown:
            raise KeyError(f"{table}: unknown column(s) {sorted(unknown)}")
        if "updated_at" in columns:
            values.setdefault("updated_at", now_iso())
        assignments = ", ".join(f"{key} = ?" for key in values)
        cur = self.execute(f"UPDATE {table} SET {assignments} WHERE id = ?",
                           (*values.values(), row_id))
        return cur.rowcount

    def delete(self, table: str, row_id: int) -> int:
        return self.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,)).rowcount

    def fetch(self, table: str, row_id: int) -> dict:
        return row_to_dict(self.query_one(f"SELECT * FROM {table} WHERE id = ?", (row_id,)))

    def fetch_all(self, table: str, where: str = "", params=(), order: str = "") -> list[dict]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        return [dict(r) for r in self.query(sql, params)]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit transaction block; nested calls join the outer one."""
        if self._migrating and getattr(_local, "in_tx", 0):
            yield self.conn
            return
        self._lock.acquire()
        depth = getattr(_local, "tx_depth", 0)
        _local.tx_depth = depth + 1
        try:
            if depth == 0:
                self.execute("BEGIN IMMEDIATE")
            yield self.conn
            if depth == 0:
                self.execute("COMMIT")
        except Exception:
            if depth == 0:
                try:
                    self.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            _local.tx_depth = depth
            self._lock.release()

    # -- maintenance --------------------------------------------------------
    def integrity_check(self) -> tuple[bool, str]:
        try:
            row = self.query_one("PRAGMA integrity_check")
            result = row[0] if row else "unknown"
            return (result == "ok"), str(result)
        except sqlite3.Error as exc:
            return False, str(exc)

    def foreign_key_check(self) -> list[dict]:
        return [dict(r) for r in self.query("PRAGMA foreign_key_check")]

    def vacuum(self) -> None:
        self.execute("VACUUM")

    def analyse(self) -> None:
        self.execute("ANALYZE")

    def backup_to(self, destination: Path | str) -> Path:
        """Online backup using the SQLite backup API (safe while in use)."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(destination))
        try:
            with self._lock:
                self.conn.backup(target)
        finally:
            target.close()
        return destination

    def restore_from(self, source: Path | str) -> None:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(source)
        # validate before touching the live database
        probe = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            row = probe.execute("PRAGMA integrity_check").fetchone()
            result = row[0] if row else "unreadable"
        except sqlite3.DatabaseError as exc:
            result = f"not a SQLite database: {exc}"
        finally:
            probe.close()
        if result != "ok":
            raise ValueError(f"Backup file is corrupt: {result}")
        self.close_all()
        tmp = self.path.with_suffix(".restore-tmp")
        shutil.copy2(source, tmp)
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.path) + suffix)
            if side.exists():
                side.unlink()
        shutil.move(str(tmp), str(self.path))

    # -- migrations ---------------------------------------------------------
    def schema_version(self) -> int:
        table = self.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if table is None:
            return 0
        return int(self.scalar("SELECT COALESCE(MAX(version),0) FROM schema_version", default=0))

    def migrate(self) -> int:
        """Apply all pending .sql migrations in filename order.

        ``executescript`` issues its own COMMIT, so the script is run outside an
        explicit transaction and the version row is written immediately after.
        A failed migration therefore leaves no half-bumped version: it is
        simply retried on the next start.
        """
        self.execute("""CREATE TABLE IF NOT EXISTS schema_version (
                            version INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            applied_at TEXT NOT NULL)""")
        current = self.schema_version()
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        applied = 0
        for file in files:
            version = int(file.stem.split("_", 1)[0])
            if version <= current:
                continue
            self.execute("PRAGMA foreign_keys = OFF")
            self.conn.executescript(file.read_text(encoding="utf-8"))
            self.execute("INSERT INTO schema_version (version, name, applied_at) "
                         "VALUES (?,?,?)", (version, file.name, now_iso()))
            self.execute("PRAGMA foreign_keys = ON")
            applied += 1
        if applied:
            self.analyse()
        return applied


# ---------------------------------------------------------------------------
# Settings store
# ---------------------------------------------------------------------------
class SettingsStore:
    """Typed key/value store persisted in the ``settings`` table."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: Any = "") -> str:
        value = self.db.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else value

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.get(key, "")
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        raw = self.get(key, "")
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key, "")
        if raw == "":
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on", "oui")

    def get_json(self, key: str, default=None):
        raw = self.get(key, "")
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any, user_id: int | None = None) -> None:
        if isinstance(value, bool):
            stored = "1" if value else "0"
        elif isinstance(value, (dict, list)):
            stored = json.dumps(value, ensure_ascii=False)
        elif value is None:
            stored = ""
        else:
            stored = str(value)
        self.db.execute(
            """INSERT INTO settings (key, value, updated_at, updated_by)
               VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                   updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
            (key, stored, now_iso(), user_id))

    def set_many(self, values: dict, user_id: int | None = None) -> None:
        with self.db.transaction():
            for key, value in values.items():
                self.set(key, value, user_id)

    def all(self) -> dict:
        return {r["key"]: r["value"] for r in self.db.query("SELECT key, value FROM settings")}

    def company(self) -> dict:
        data = dict(DEFAULT_COMPANY)
        for key in DEFAULT_COMPANY:
            stored = self.get(key, "")
            if stored:
                data[key] = stored
        return data

    def ensure_defaults(self, user_id: int | None = None) -> None:
        from ..config import (DEFAULT_CURRENCY_CODE, DEFAULT_CURRENCY_SYMBOL,
                              DEFAULT_DATE_FORMAT, DEFAULT_LOCALE, DEFAULT_TIMEZONE,
                              DEFAULT_VAT_RATE, TRIAL_DAYS)

        defaults = {
            "app.version": APP_VERSION,
            "company.company_name": DEFAULT_COMPANY["company_name"],
            "locale.language": DEFAULT_LOCALE,
            "locale.currency_code": DEFAULT_CURRENCY_CODE,
            "locale.currency_symbol": DEFAULT_CURRENCY_SYMBOL,
            "locale.timezone": DEFAULT_TIMEZONE,
            "locale.date_format": DEFAULT_DATE_FORMAT,
            "tax.default_vat_rate": DEFAULT_VAT_RATE,
            "tax.vat_standard": 20.0,
            "tax.vat_reduced": 10.0,
            "tax.vat_zero": 0.0,
            "appearance.theme": "light",
            "appearance.accent": "#0F766E",
            "appearance.sidebar_collapsed": False,
            "backup.auto_enabled": True,
            "backup.location": "",
            "backup.keep": 30,
            "backup.hour": 20,
            "backup.minute": 0,
            "backup.last_run": "",
            "print.default_printer": "",
            "print.receipt_printer": "",
            "print.invoice_paper": "a4",
            "print.receipt_paper": "thermal80",
            "print.copies_receipt": 1,
            "print.copies_invoice": 1,
            "pos.auto_open_drawer": False,
            "pos.allow_negative_stock": False,
            "pos.require_cash_session": True,
            "pos.receipt_footer": "Merci de votre visite - \u00c0 bient\u00f4t",
            "doc.show_logo": True,
            "doc.show_ice": True,
            "license.trial_started": "",
            "license.trial_days": TRIAL_DAYS,
            "security.session_timeout_minutes": 0,
        }
        with self.db.transaction():
            for key, value in defaults.items():
                if self.get(key, None) is None or self.db.scalar(
                        "SELECT 1 FROM settings WHERE key=?", (key,)) is None:
                    self.set(key, value, user_id)
        # company profile
        for key, value in DEFAULT_COMPANY.items():
            full = f"company.{key}"
            if self.db.scalar("SELECT 1 FROM settings WHERE key=?", (full,)) is None:
                self.set(full, value, user_id)

    # convenience shortcuts
    def currency_symbol(self) -> str:
        return self.get("locale.currency_symbol", "DH")

    def language(self) -> str:
        return self.get("locale.language", "fr")

    def default_vat(self) -> float:
        return self.get_float("tax.default_vat_rate", 20.0)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class AuditLog:
    """Append-only journal of the important actions."""

    def __init__(self, db: Database):
        self.db = db

    def record(self, action: str, *, user_id: int | None = None, username: str = "",
               entity_type: str = "", entity_id: int | None = None, details: str = "") -> int:
        try:
            hostname = platform.node()
        except Exception:  # pragma: no cover - platform oddities
            hostname = ""
        return self.db.insert(
            "audit_logs",
            timestamp=now_iso(),
            user_id=user_id,
            username=username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=str(details)[:2000],
            ip_address="127.0.0.1",
            hostname=hostname,
        )

    def recent(self, limit: int = 200, action: str = "", user_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params: list[Any] = []
        if action:
            sql += " AND action = ?"
            params.append(action)
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.db.query(sql, params)]

    def purge_older_than(self, days: int) -> int:
        return self.db.execute(
            "DELETE FROM audit_logs WHERE timestamp < datetime('now', ?)",
            (f"-{int(days)} days",)).rowcount


# ---------------------------------------------------------------------------
# Application container
# ---------------------------------------------------------------------------
class App:
    """Root object holding the database and the shared services.

    A single instance is created by the application entry point and passed to
    every screen, which keeps the dependency graph explicit and testable.
    """

    def __init__(self, db: Database):
        self.db = db
        self.settings = SettingsStore(db)
        self.audit = AuditLog(db)
        self.current_user: dict | None = None
        self.current_session: dict | None = None

    @property
    def user_id(self) -> int | None:
        return self.current_user.get("id") if self.current_user else None

    @property
    def username(self) -> str:
        return (self.current_user or {}).get("username", "")

    def log(self, action: str, **kwargs) -> None:
        kwargs.setdefault("user_id", self.user_id)
        kwargs.setdefault("username", self.username)
        try:
            self.audit.record(action, **kwargs)
        except sqlite3.Error:
            traceback.print_exc()


def open_database(path: Path | str, migrate: bool = True) -> Database:
    db = Database(path)
    if migrate:
        db.migrate()
    return db
