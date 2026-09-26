"""Phase 1 - database, migrations, settings, audit log."""

from __future__ import annotations

import sqlite3

import pytest

from mustacom.db.database import App, SettingsStore, open_database

EXPECTED_TABLES = {
    "users", "roles", "permissions", "role_permissions", "user_permissions",
    "products", "categories", "brands", "customers", "suppliers", "services",
    "sales", "sale_items", "sale_payments", "held_sales", "quotes", "quote_items",
    "orders", "order_items", "delivery_notes", "delivery_items", "route_notes",
    "route_note_items", "return_notes", "return_items", "invoices", "invoice_items",
    "credit_notes", "credit_note_items", "payments", "payment_allocations",
    "purchases", "purchase_items", "purchase_receipts", "purchase_receipt_items",
    "purchase_invoices", "stock_movements", "inventories", "inventory_items",
    "repairs", "repair_items", "cash_sessions", "cash_movements", "expenses",
    "documents", "licenses", "settings", "audit_logs", "vehicles", "drivers",
    "document_sequences", "schema_version",
}


def table_names(db) -> set[str]:
    return {r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def test_migration_creates_every_table(db):
    assert EXPECTED_TABLES <= table_names(db)
    assert db.schema_version() >= 1


def test_migration_is_idempotent(db):
    assert db.migrate() == 0
    assert db.schema_version() == 1


def test_integrity_and_foreign_keys_are_enforced(db):
    ok, message = db.integrity_check()
    assert ok, message
    with pytest.raises(sqlite3.IntegrityError):
        db.insert("sale_items", sale_id=999999, label="orphan")


def test_insert_rejects_unknown_columns(db):
    with pytest.raises(KeyError):
        db.insert("audit_logs", status="active")


def test_insert_only_sets_audit_columns_that_exist(db):
    role_id = db.insert("roles", code="admin", name="Administrateur")
    assert db.table_columns("role_permissions") == {"role_id", "permission_id"}
    permission_id = db.insert("permissions", module="products", action="view")
    # table without created_at/updated_at/status must still accept a plain insert
    db.insert("role_permissions", role_id=role_id, permission_id=permission_id)
    assert db.scalar("SELECT COUNT(*) FROM role_permissions") == 1


def test_transaction_rolls_back_on_error(db):
    db.insert("brands", name="Rolled")
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.insert("brands", name="Doomed")
            raise RuntimeError("boom")
    names = {r["name"] for r in db.query("SELECT name FROM brands")}
    assert "Rolled" in names
    assert "Doomed" not in names


def test_backup_and_restore_roundtrip(tmp_path):
    source = open_database(tmp_path / "a.db")
    source.insert("brands", name="Canon")
    archive = tmp_path / "backup.zip"
    source.backup_to(archive.with_suffix(".db"))
    assert archive.with_suffix(".db").exists()

    target = open_database(tmp_path / "b.db")
    assert target.scalar("SELECT COUNT(*) FROM brands") == 0
    target.restore_from(archive.with_suffix(".db"))
    assert target.scalar("SELECT COUNT(*) FROM brands") == 1
    source.close_all()
    target.close_all()


def test_restore_rejects_corrupt_file(tmp_path):
    database = open_database(tmp_path / "a.db")
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a sqlite file at all" * 10)
    with pytest.raises(ValueError):
        database.restore_from(broken)


def test_settings_store_types(db):
    settings = SettingsStore(db)
    settings.ensure_defaults()
    settings.set("test.bool", True)
    settings.set("test.int", 42)
    settings.set("test.float", 19.99)
    settings.set("test.json", {"a": [1, 2, 3]})
    settings.set("test.none", None)
    assert settings.get_bool("test.bool") is True
    assert settings.get_int("test.int") == 42
    assert settings.get_float("test.float") == pytest.approx(19.99)
    assert settings.get_json("test.json") == {"a": [1, 2, 3]}
    assert settings.get("test.none") == ""


def test_default_company_profile_is_mustacom(db):
    settings = SettingsStore(db)
    settings.ensure_defaults()
    company = settings.company()
    assert company["company_name"] == "MUSTACOM"
    assert company["company_phone"] == "07 08 78 51 53"
    assert company["company_email"] == "mustacom.services@gmail.com"
    assert "Tinghir" in company["company_city"]
    assert "Tawzakt" in company["company_address"]
    assert settings.get("locale.timezone") == "Africa/Casablanca"
    assert settings.get("locale.currency_code") == "MAD"
    assert settings.language() == "fr"


def test_audit_log_records_and_filters(db):
    app = App(db)
    app.audit.record("login", username="admin", details="ok")
    app.audit.record("invoice.create", username="admin", entity_type="invoice", entity_id=7)
    assert len(app.audit.recent()) == 2
    assert len(app.audit.recent(action="login")) == 1
    assert app.audit.recent(action="invoice.create")[0]["entity_id"] == 7


def test_audit_purge(db):
    app = App(db)
    app.audit.record("old.action", username="admin")
    db.execute("UPDATE audit_logs SET timestamp = datetime('now','-400 days')")
    assert app.audit.purge_older_than(365) == 1
    assert app.audit.recent() == []
