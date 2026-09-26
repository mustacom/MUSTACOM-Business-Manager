"""Phase 9 - license / serial key activation system."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from mustacom.core import license as lic
from mustacom.core.license import (compute_serial_key, is_valid_key_format, issue_license,
                                   machine_id, normalize_key, read_license_file,
                                   verify_payload)

SECRET = "TEST-SECRET"


def test_machine_id_is_stable_and_short():
    first = machine_id()
    assert first == machine_id()
    assert len(first) == 12
    assert first.isalnum()


def test_serial_key_format():
    payload, key, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                            "professional", secret=SECRET)
    assert key.startswith("MUST-")
    assert len(key) == 24                      # MUST-XXXX-XXXX-XXXX-XXXX
    assert [len(group) for group in key.split("-")] == [4, 4, 4, 4, 4]
    assert is_valid_key_format(key)
    assert is_valid_key_format(key.lower().replace("-", " "))
    assert is_valid_key_format("MUST-AAAA-BBBB-CCCC-DDDD")       # well formed
    assert not is_valid_key_format("XXXX-AAAA-BBBB-CCCC-DDDD")   # wrong prefix
    assert not is_valid_key_format("MUST-AAAA-BBBB-CCCC")        # too short
    assert not is_valid_key_format("")                           # empty
    # note: normalize_key() deliberately re-groups sloppy input, so a 5th
    # group is folded in rather than rejected - format check != authenticity


def test_normalize_key_accepts_sloppy_input():
    assert normalize_key("must-ABCD EFGH.JKMN.PQRS") == "MUST-ABCD-EFGH-JKMN-PQRS"
    assert normalize_key("MUSTABCDEFGHJKMNPQRS") == "MUST-ABCD-EFGH-JKMN-PQRS"
    assert is_valid_key_format("must abcdefghjkmnpqrs")


def test_keys_are_unique_per_customer():
    keys = set()
    for company in ("MUSTACOM", "Papeterie Atlas", "Ecole Ibn Sina", "Copy Center"):
        _, key, _ = issue_license(company, "user", machine_id(), "standard", secret=SECRET)
        keys.add(key)
    assert len(keys) == 4                      # no universal key


def test_key_changes_with_license_type_and_expiry():
    machine = machine_id()
    _, standard, _ = issue_license("X", "u", machine, "standard", 365, secret=SECRET)
    _, professional, _ = issue_license("X", "u", machine, "professional", 730, secret=SECRET)
    assert standard != professional


def test_payload_signature_verification():
    payload, key, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                            "enterprise", secret=SECRET)
    assert verify_payload(payload, signature, SECRET)
    tampered = lic.LicensePayload(**{**payload.__dict__, "license_type": "enterprise",
                                     "expires_at": "2099-12-31"})
    assert not verify_payload(tampered, signature, SECRET)
    assert not verify_payload(payload, signature, "WRONG-SECRET")


def test_permanent_license_has_no_expiry():
    payload, _, _ = issue_license("X", "u", machine_id(), "enterprise", secret=SECRET)
    assert payload.expires_at == ""
    assert payload.is_permanent
    assert payload.days_left() is None
    assert payload.max_devices == 10


def test_trial_is_30_days():
    payload, _, _ = issue_license("X", "u", machine_id(), "trial", secret=SECRET)
    assert payload.license_type == "trial"
    assert payload.days_left() == 30


def test_offline_activation_file_roundtrip(tmp_path, services, monkeypatch):
    # the shipped app verifies with the build-time master secret
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    machine = machine_id()
    payload, key, signature = issue_license("MUSTACOM", "Ahmed Benali", machine,
                                            "professional", secret=SECRET)
    path = lic.export_license_file(payload, signature, tmp_path / "mustacom")
    assert path.suffix == ".mustacomlic"

    status = services.license.activate_with_file(path, secret=SECRET)
    assert status.active and not status.blocked
    assert status.license_type == "professional"
    assert status.company == "MUSTACOM"
    assert status.key == key

    loaded, loaded_signature = read_license_file(path)
    assert loaded.company == "MUSTACOM"
    assert loaded_signature == signature


def test_license_file_for_another_machine_is_refused(tmp_path, services):
    payload, _, signature = issue_license("Autre SARL", "Ali", "ZZZZ9999888877",
                                          "standard", secret=SECRET)
    path = lic.export_license_file(payload, signature, tmp_path / "other")
    status = services.license.activate_with_file(path, secret=SECRET)
    assert not status.active
    assert status.blocked
    assert "ZZZZ9999888877" in status.message


def test_tampered_license_file_is_refused(tmp_path, services):
    payload, _, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                          "standard", secret=SECRET)
    path = lic.export_license_file(payload, signature, tmp_path / "mustacom")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["payload"]["license_type"] = "enterprise"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        services.license.activate_with_file(path, secret=SECRET)


def test_unactivated_state_is_blocked(services):
    status = services.license.status()
    assert not status.active
    assert status.blocked


def test_trial_can_be_started_and_expires(services):
    services.license.start_trial("MUSTACOM", "Ahmed")
    status = services.license.status()
    assert status.active
    assert status.license_type == "trial"
    assert status.days_left == 30
    # force the trial into the past (both the counter and the issued key)
    past = (datetime.now() - timedelta(days=40)).date().isoformat()
    services.settings.set("license.trial_started", past)
    row = services.db.query_one("SELECT * FROM licenses")
    services.db.update("licenses", row["id"], expires_at=past)
    status = services.license.status()
    assert status.expired and status.blocked
    assert status.days_left <= -10


def test_expiring_license_warns(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    expires = (datetime.now() + timedelta(days=5)).date().isoformat()
    payload = lic.LicensePayload(company="MUSTACOM", user="Ahmed", machine_id=machine_id(),
                                 license_type="standard", issued_at=datetime.now().date().isoformat(),
                                 expires_at=expires, max_devices=1, license_id="ABC123")
    signature = lic._sign(payload, SECRET)
    services.license.save(payload, signature, compute_serial_key(payload, SECRET))
    status = services.license.status()
    assert status.expiring_soon
    assert status.days_left == 5
    assert not status.blocked


def test_expired_license_blocks_after_grace(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    expires = (datetime.now() - timedelta(days=10)).date().isoformat()
    payload = lic.LicensePayload(company="MUSTACOM", user="Ahmed", machine_id=machine_id(),
                                 license_type="standard", expires_at=expires, license_id="X1")
    services.license.save(payload, lic._sign(payload, SECRET),
                          compute_serial_key(payload, SECRET))
    status = services.license.status()
    assert status.expired and status.blocked


def test_renew_extends_expiry(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    expires = (datetime.now() + timedelta(days=3)).date().isoformat()
    payload = lic.LicensePayload(company="MUSTACOM", user="Ahmed", machine_id=machine_id(),
                                 license_type="standard", expires_at=expires, license_id="X2")
    services.license.save(payload, lic._sign(payload, SECRET),
                          compute_serial_key(payload, SECRET))
    status = services.license.renew(365, secret=SECRET)
    assert status.days_left == 368
    assert not status.blocked


def test_deactivate_device(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    payload, key, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                            "standard", secret=SECRET)
    services.license.save(payload, signature, key)
    assert services.license.status().active
    services.license.deactivate()
    status = services.license.status()
    assert not status.active


def test_activate_by_key_after_reinstall(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    payload, key, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                            "professional", secret=SECRET)
    services.license.save(payload, signature, key)
    services.license.deactivate()
    status = services.license.activate("MUSTACOM", "Ahmed", key, secret=SECRET)
    assert status.active
    assert status.license_type == "professional"


def test_machine_request_file(tmp_path):
    path = lic.export_machine_request(tmp_path / "req", "MUSTACOM", "Ahmed")
    assert path.suffix == ".mustacomreq"
    data = lic.read_machine_request(path)
    assert data["machine_id"] == machine_id()
    assert data["company"] == "MUSTACOM"


def test_clock_rollback_is_detected(services, monkeypatch):
    monkeypatch.setenv("MUSTACOM_LICENSE_SECRET", SECRET)
    payload, key, signature = issue_license("MUSTACOM", "Ahmed", machine_id(),
                                            "standard", secret=SECRET)
    services.license.save(payload, signature, key)
    future = (datetime.now() + timedelta(days=30)).date().isoformat()
    services.settings.set("license.last_seen", future)
    status = services.license.status()
    assert status.clock_suspect
    assert status.blocked
