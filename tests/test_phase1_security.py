"""Phase 1 - authentication, permissions, password hashing."""

from __future__ import annotations

import pytest

from mustacom.core.auth import MAX_FAILED_ATTEMPTS, ROLE_TEMPLATES
from mustacom.core.security import (ValidationError, hash_password, hasher_name,
                                    password_strength, validate_ice, validate_email,
                                    validate_username, verify_password)


def test_password_hashing_is_salted_and_verifiable():
    first = hash_password("Secret!2345")
    second = hash_password("Secret!2345")
    assert first != second                       # random salt
    assert "Secret!2345" not in first            # never stored in clear
    assert verify_password("Secret!2345", first)
    assert not verify_password("Secret!2346", first)
    assert not verify_password("Secret!2345", "garbage")
    assert not verify_password("", first)
    assert hasher_name() in ("argon2id", "pbkdf2_sha256")


def test_password_strength_scores():
    assert password_strength("abc")[0] <= 1
    assert password_strength("Str0ng!Passw0rd-2026")[0] == 4


def test_input_validation():
    assert validate_username("caissier.01") == "caissier.01"
    with pytest.raises(ValidationError):
        validate_username("ab")
    with pytest.raises(ValidationError):
        validate_username("has space")
    assert validate_email("mustacom.services@gmail.com") == "mustacom.services@gmail.com"
    with pytest.raises(ValidationError):
        validate_email("not-an-email")
    assert validate_email("") == ""
    assert validate_ice("001234567000089") == "001234567000089"
    with pytest.raises(ValidationError):
        validate_ice("12345")


def test_roles_are_seeded_with_their_templates(services):
    codes = {r["code"] for r in services.db.query("SELECT code FROM roles")}
    assert codes == set(ROLE_TEMPLATES)
    admin_perms = services.auth.role_permissions("admin")
    assert ("products", "delete") in admin_perms
    assert ("license", "edit") in admin_perms
    cashier_perms = services.auth.role_permissions("cashier")
    assert ("pos", "create") in cashier_perms
    assert ("products", "delete") not in cashier_perms
    technician_perms = services.auth.role_permissions("technician")
    assert ("repairs", "validate") in technician_perms
    assert ("invoices", "create") not in technician_perms


def test_create_user_and_login(services):
    services.auth.create_user("caisse1", "Caisse!2345", "Fatima Zahra", "cashier")
    assert services.auth.username_exists("caisse1")
    session = services.auth.login("caisse1", "Caisse!2345")
    assert session.username == "caisse1"
    assert session.role_code == "cashier"
    assert session.has("pos", "create")
    assert not session.has("users", "create")


def test_duplicate_username_rejected(services):
    services.auth.create_user("dup", "Dup!23456", "Dup", "cashier")
    with pytest.raises(ValidationError):
        services.auth.create_user("dup", "Other!2345", "Autre", "cashier")


def test_wrong_password_and_lockout(services):
    services.auth.create_user("lock", "Lock!23456", "Lock", "cashier")
    for attempt in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(ValidationError):
            services.auth.login("lock", "wrong-password")
    user = services.auth.get_user_by_name("lock")
    assert user["locked_until"]
    with pytest.raises(ValidationError):
        services.auth.login("lock", "Lock!23456")


def test_disabled_account_cannot_login(services):
    user_id = services.auth.create_user("off", "Off!234567", "Off", "cashier")
    services.auth.update_user(user_id, is_active=False)
    with pytest.raises(ValidationError):
        services.auth.login("off", "Off!234567")


def test_change_password_flow(services):
    user_id = services.auth.create_user("chg", "Old!234567", "Chg", "cashier")
    with pytest.raises(ValidationError):
        services.auth.change_password(user_id, "bad", "New!234567")
    services.auth.change_password(user_id, "Old!234567", "New!234567")
    assert services.auth.login("chg", "New!234567").username == "chg"
    with pytest.raises(ValidationError):
        services.auth.login("chg", "Old!234567")


def test_per_user_permission_override(services):
    user_id = services.auth.create_user("tech1", "Tech!23456", "Technicien", "technician")
    session = services.auth.build_session(services.auth.get_user(user_id))
    assert not session.has("invoices", "create")
    services.auth.set_user_override(user_id, "invoices", "create", True)
    session = services.auth.build_session(services.auth.get_user(user_id))
    assert session.has("invoices", "create")
    services.auth.set_user_override(user_id, "invoices", "create", False)
    session = services.auth.build_session(services.auth.get_user(user_id))
    assert not session.has("invoices", "create")


def test_admin_always_has_everything(services):
    user_id = services.auth.create_user("root", "Root!23456", "Root", "admin")
    session = services.auth.build_session(services.auth.get_user(user_id))
    for module in ("license", "users", "settings", "backup", "reports"):
        for action in ("view", "create", "edit", "delete", "print", "export", "validate"):
            assert session.has(module, action), (module, action)


def test_set_role_permissions_persists(services):
    services.auth.set_role_permissions("cashier", {("pos", "create"), ("pos", "view")})
    assert services.auth.role_permissions("cashier") == {("pos", "create"), ("pos", "view")}
    # administrator rights cannot be trimmed
    services.auth.set_role_permissions("admin", {("pos", "view")})
    assert ("users", "delete") in services.auth.role_permissions("admin")


def test_login_records_last_login(services):
    services.auth.create_user("stamp", "Stamp!2345", "Stamp", "cashier")
    assert not services.auth.get_user_by_name("stamp")["last_login_at"]
    services.auth.login("stamp", "Stamp!2345")
    assert services.auth.get_user_by_name("stamp")["last_login_at"]


def test_session_expiry(admin_session):
    admin_session.timeout_minutes = 30
    assert not admin_session.is_expired()
    admin_session.last_activity = "2000-01-01 00:00:00"
    assert admin_session.is_expired()
