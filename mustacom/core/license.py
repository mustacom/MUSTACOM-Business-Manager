"""License / serial key activation system.

How it works
------------
1. The application computes a stable **machine identifier** from hardware and
   OS data (on Windows the ``MachineGuid`` registry value when available).
2. A license is a *payload* (company, user, machine id, type, expiry, device
   count, ...) signed with **HMAC-SHA256** using the vendor master secret.
3. The human readable serial key is the first 10 bytes of that signature,
   base32 encoded with an unambiguous alphabet and grouped as
   ``MUST-XXXX-XXXX-XXXX-XXXX``.  Because the signature is derived from the
   payload, a key is only valid for the exact machine it was issued for and
   for the exact license type/expiry it was issued with - there is no
   universal key.
4. Offline activation ships the complete signed payload in a
   ``.mustacomlic`` file that the customer imports.

The shipped application only ever *verifies* signatures.  Key generation
(``issue_license``) is available to the vendor through the admin License
screen and the ``tools/keygen.py`` CLI; override ``MUSTACOM_LICENSE_SECRET``
at build time so the master secret is not the public development default.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import platform
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import (EXPIRY_WARNING_DAYS, LICENSE_FILE_EXT, LICENSE_KEY_PREFIX,
                      LICENSE_TYPES, MACHINE_REQUEST_EXT, TRIAL_DAYS, license_secret)

# Alphabet without I, L, O, U to avoid transcription mistakes.
_KEY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ0123456789"
# base32 output alphabet -> unambiguous key alphabet (no I, L, O, U)
_B32_TO_KEY = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", _KEY_ALPHABET)
_KEY_GROUP = 4
_KEY_GROUPS = 4
KEY_RE = re.compile(r"^MUST(?:-[ABCDEFGHJKMNPQRSTVWXYZ0-9]{4}){4}$")

GRACE_DAYS = 3
CLOCK_ROLLBACK_HOURS = 48


# ---------------------------------------------------------------------------
# machine identifier
# ---------------------------------------------------------------------------
def _windows_machine_guid() -> str:
    if platform.system() != "Windows":
        return ""
    try:
        output = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
            capture_output=True, text=True, timeout=5)
        for line in output.stdout.splitlines():
            if "MachineGuid" in line:
                return line.split()[-1].strip()
    except Exception:
        pass
    return ""


def _read_linux_machine_id() -> str:
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def machine_fingerprint() -> str:
    """Raw, human-readable fingerprint of this workstation."""
    parts = [
        _windows_machine_guid(),
        _read_linux_machine_id(),
        platform.node(),
        platform.machine(),
        platform.processor(),
        platform.system(),
        uuid.getnode() and format(uuid.getnode(), "x"),
    ]
    return "|".join(p for p in parts if p)


def machine_id() -> str:
    """Short stable identifier shown on the activation screen."""
    digest = hashlib.sha256(("MUSTACOM::" + machine_fingerprint()).encode("utf-8")).digest()
    raw = base64.b32encode(digest).decode("ascii").rstrip("=")
    return raw.translate(_B32_TO_KEY)[:12]


# ---------------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------------
@dataclass
class LicensePayload:
    company: str = ""
    user: str = ""
    machine_id: str = ""
    license_type: str = "trial"
    issued_at: str = ""
    expires_at: str = ""            # empty = permanent
    max_devices: int = 1
    license_id: str = ""
    version: int = 1
    features: list[str] = field(default_factory=list)

    def canonical(self) -> str:
        data = asdict(self)
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def is_permanent(self) -> bool:
        return not self.expires_at

    def days_left(self, today: datetime | None = None) -> int | None:
        if self.is_permanent:
            return None
        today = today or datetime.now()
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace(" ", "T"))
        except ValueError:
            return -1
        return (expiry.date() - today.date()).days


# ---------------------------------------------------------------------------
# signing / verification
# ---------------------------------------------------------------------------
def _sign(payload: LicensePayload, secret: str | None = None) -> str:
    secret = secret or license_secret()
    return hmac.new(secret.encode("utf-8"), payload.canonical().encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _encode_key(digest_hex: str) -> str:
    raw = bytes.fromhex(digest_hex[:20])
    encoded = base64.b32encode(raw).decode("ascii").rstrip("=")
    translated = encoded.translate(_B32_TO_KEY)
    groups = [translated[i:i + _KEY_GROUP] for i in range(0, _KEY_GROUP * _KEY_GROUPS, _KEY_GROUP)]
    return LICENSE_KEY_PREFIX + "-" + "-".join(groups)


def normalize_key(key: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", key or "").upper()
    if cleaned.startswith(LICENSE_KEY_PREFIX) and len(cleaned) == 4 + _KEY_GROUP * _KEY_GROUPS:
        body = cleaned[4:]
        return LICENSE_KEY_PREFIX + "-" + "-".join(
            body[i:i + _KEY_GROUP] for i in range(0, len(body), _KEY_GROUP))
    return cleaned


def is_valid_key_format(key: str) -> bool:
    return bool(KEY_RE.match(normalize_key(key)))


def compute_serial_key(payload: LicensePayload, secret: str | None = None) -> str:
    """Serial key derived from the signed payload (the vendor side)."""
    return _encode_key(_sign(payload, secret))


def verify_payload(payload: LicensePayload, signature: str,
                   secret: str | None = None) -> bool:
    expected = _sign(payload, secret)
    return hmac.compare_digest(expected, (signature or "").lower())


# ---------------------------------------------------------------------------
# issuing (vendor side)
# ---------------------------------------------------------------------------
def make_payload(company: str, user: str, machine: str, license_type: str = "trial",
                 duration_days: int | None = None, max_devices: int | None = None,
                 issued_at: datetime | None = None) -> LicensePayload:
    license_type = (license_type or "trial").lower()
    if license_type not in LICENSE_TYPES:
        raise ValueError(f"unknown license type: {license_type}")
    issued_at = issued_at or datetime.now()

    if duration_days is None:
        duration_days = {
            "trial": TRIAL_DAYS,
            "standard": 365,
            "professional": 730,
            "enterprise": 0,
        }[license_type]
    if max_devices is None:
        max_devices = {"trial": 1, "standard": 1, "professional": 3, "enterprise": 10}[license_type]

    expires_at = ""
    if duration_days:
        expires_at = (issued_at + timedelta(days=duration_days)).date().isoformat()

    return LicensePayload(
        company=company.strip(),
        user=user.strip(),
        machine_id=machine.strip(),
        license_type=license_type,
        issued_at=issued_at.date().isoformat(),
        expires_at=expires_at,
        max_devices=max(1, int(max_devices)),
        license_id=uuid.uuid4().hex[:12].upper(),
    )


def issue_license(company: str, user: str, machine: str, license_type: str = "trial",
                  duration_days: int | None = None, max_devices: int | None = None,
                  secret: str | None = None) -> tuple[LicensePayload, str, str]:
    """Return (payload, serial_key, signature)."""
    payload = make_payload(company, user, machine, license_type, duration_days, max_devices)
    signature = _sign(payload, secret)
    return payload, _encode_key(signature), signature


def export_license_file(payload: LicensePayload, signature: str, destination: Path | str,
                        secret: str | None = None) -> Path:
    """Write the offline activation file for a customer."""
    destination = Path(destination)
    if destination.suffix != LICENSE_FILE_EXT:
        destination = destination.with_suffix(LICENSE_FILE_EXT)
    envelope = {
        "application": "MUSTACOM BUSINESS MANAGER",
        "payload": asdict(payload),
        "signature": signature,
        "checksum": hashlib.sha256((payload.canonical() + signature).encode()).hexdigest(),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
    return destination


def read_license_file(source: Path | str) -> tuple[LicensePayload, str]:
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    if data.get("application") != "MUSTACOM BUSINESS MANAGER":
        raise ValueError("fichier de licence non reconnu")
    raw = data["payload"]
    known = {f.name for f in __import__("dataclasses").fields(LicensePayload)}
    payload = LicensePayload(**{k: v for k, v in raw.items() if k in known})
    checksum = hashlib.sha256(
        (payload.canonical() + data.get("signature", "")).encode()).hexdigest()
    if checksum != data.get("checksum"):
        raise ValueError("fichier de licence alt\u00e9r\u00e9")
    return payload, data["signature"]


def export_machine_request(destination: Path | str, company: str = "", user: str = "") -> Path:
    """File the customer sends to the vendor to obtain a license offline."""
    destination = Path(destination)
    if destination.suffix != MACHINE_REQUEST_EXT:
        destination = destination.with_suffix(MACHINE_REQUEST_EXT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        "application": "MUSTACOM BUSINESS MANAGER",
        "machine_id": machine_id(),
        "fingerprint": hashlib.sha256(machine_fingerprint().encode()).hexdigest(),
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "company": company,
        "user": user,
        "generated_at": datetime.now().isoformat(sep=" "),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return destination


def read_machine_request(source: Path | str) -> dict:
    return json.loads(Path(source).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# runtime status
# ---------------------------------------------------------------------------
@dataclass
class LicenseStatus:
    active: bool = False
    license_type: str = ""
    key: str = ""
    company: str = ""
    user: str = ""
    machine_id: str = ""
    activated_at: str = ""
    expires_at: str = ""
    max_devices: int = 1
    days_left: int | None = None
    expired: bool = False
    expiring_soon: bool = False
    in_grace: bool = False
    clock_suspect: bool = False
    message: str = ""
    blocked: bool = False

    @property
    def label(self) -> str:
        return {
            "trial": "Essai", "standard": "Standard",
            "professional": "Professionnelle", "enterprise": "Entreprise",
        }.get(self.license_type, self.license_type.title())


class LicenseService:
    """Persisted license state and validation."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    # -- persistence --------------------------------------------------------
    def _row(self) -> dict:
        row = self.db.query_one("SELECT * FROM licenses ORDER BY id DESC LIMIT 1")
        return dict(row) if row else {}

    def save(self, payload: LicensePayload, signature: str, key: str) -> None:
        existing = self._row()
        values = dict(
            license_key=key,
            company_name=payload.company,
            user_name=payload.user,
            machine_id=payload.machine_id,
            license_type=payload.license_type,
            activated_at=datetime.now().date().isoformat(),
            expires_at=payload.expires_at,
            max_devices=payload.max_devices,
            activated_devices=1,
            is_active=1,
            payload=json.dumps(asdict(payload), ensure_ascii=False),
            signature=signature,
            status="active",
        )
        if existing:
            self.db.update("licenses", existing["id"], **values)
        else:
            self.db.insert("licenses", **values)
        self.settings.set("license.last_check", datetime.now().isoformat(sep=" "))

    def deactivate(self) -> None:
        row = self._row()
        if row:
            self.db.update("licenses", row["id"], is_active=0, status="deactivated")

    def record_seen(self) -> None:
        self.settings.set("license.last_seen", datetime.now().date().isoformat())

    # -- trial --------------------------------------------------------------
    def start_trial(self, company: str, user: str) -> LicensePayload:
        payload, key, signature = issue_license(company, user, machine_id(), "trial",
                                                TRIAL_DAYS, 1)
        self.save(payload, signature, key)
        self.settings.set("license.trial_started", datetime.now().date().isoformat())
        return payload

    def trial_days_left(self) -> int:
        started = self.settings.get("license.trial_started", "")
        if not started:
            return TRIAL_DAYS
        try:
            start = datetime.fromisoformat(started.replace(" ", "T")).date()
        except ValueError:
            return TRIAL_DAYS
        return TRIAL_DAYS - (datetime.now().date() - start).days

    # -- activation ---------------------------------------------------------
    def activate(self, company: str, user: str, key: str,
                 secret: str | None = None) -> LicenseStatus:
        """Activate with a serial key.

        The serial key alone identifies the payload through the vendor's key
        register; because the shipped app cannot rebuild arbitrary payloads,
        activation by key alone requires the accompanying ``.mustacomlic``
        file when the payload is not already known.  ``activate_with_file`` is
        therefore the primary path, and this method handles the case where the
        payload was previously stored (re-activation after a reinstall).
        """
        key = normalize_key(key)
        if not is_valid_key_format(key):
            return LicenseStatus(message="Format de cl\u00e9 invalide (MUST-XXXX-XXXX-XXXX-XXXX)",
                                 blocked=True)
        row = self._row()
        if row and row.get("license_key") == key and row.get("payload"):
            payload = LicensePayload(**json.loads(row["payload"]))
            if not verify_payload(payload, row.get("signature", ""), secret):
                return LicenseStatus(message="Signature de licence invalide", blocked=True)
            if payload.machine_id and payload.machine_id != machine_id():
                return LicenseStatus(message="Cette licence est li\u00e9e \u00e0 un autre poste",
                                     blocked=True)
            payload.company = company or payload.company
            payload.user = user or payload.user
            signature = _sign(payload, secret)
            self.save(payload, signature, key)
            return self.status()
        return LicenseStatus(
            message="Cl\u00e9 inconnue sur ce poste. Importez le fichier d'activation "
                    "fourni par MUSTACOM (bouton Activer hors ligne).",
            blocked=True)

    def activate_with_file(self, source: Path | str, secret: str | None = None) -> LicenseStatus:
        payload, signature = read_license_file(source)
        if not verify_payload(payload, signature, secret):
            return LicenseStatus(message="Signature de licence invalide", blocked=True)
        if payload.machine_id and payload.machine_id != machine_id():
            return LicenseStatus(
                message=f"Licence \u00e9mise pour le poste {payload.machine_id}, "
                        f"ce poste est {machine_id()}", blocked=True)
        self.save(payload, signature, compute_serial_key(payload, secret))
        return self.status()

    # -- status -------------------------------------------------------------
    def status(self) -> LicenseStatus:
        row = self._row()
        if not row or not row.get("is_active"):
            trial_left = self.trial_days_left()
            started = self.settings.get("license.trial_started", "")
            if started and trial_left <= 0:
                return LicenseStatus(license_type="trial", expired=True, blocked=True,
                                     days_left=0, message="P\u00e9riode d'essai termin\u00e9e")
            return LicenseStatus(license_type="trial" if started else "",
                                 days_left=trial_left if started else None,
                                 message="Logiciel non activ\u00e9", blocked=not started)

        payload_data = json.loads(row.get("payload") or "{}")
        known = {f.name for f in __import__("dataclasses").fields(LicensePayload)}
        payload = LicensePayload(**{k: v for k, v in payload_data.items() if k in known})
        signature_ok = verify_payload(payload, row.get("signature", ""))
        current_machine = machine_id()
        machine_ok = (not payload.machine_id) or payload.machine_id == current_machine

        status = LicenseStatus(
            active=True,
            license_type=payload.license_type,
            key=row.get("license_key", ""),
            company=payload.company,
            user=payload.user,
            machine_id=payload.machine_id or current_machine,
            activated_at=row.get("activated_at", ""),
            expires_at=payload.expires_at,
            max_devices=payload.max_devices,
        )

        if not signature_ok:
            status.message = "Signature de licence invalide"
            status.blocked = True
            return status
        if not machine_ok:
            status.message = f"Licence li\u00e9e au poste {payload.machine_id}"
            status.blocked = True
            return status

        # clock rollback detection
        last_seen = self.settings.get("license.last_seen", "")
        if last_seen:
            try:
                last = datetime.fromisoformat(last_seen.replace(" ", "T")).date()
                if (last - datetime.now().date()).days * 24 > CLOCK_ROLLBACK_HOURS:
                    status.clock_suspect = True
                    status.message = "Horloge syst\u00e8me incoh\u00e9rente"
                    status.blocked = True
                    self.record_seen()
                    return status
            except ValueError:
                pass
        self.record_seen()

        days = payload.days_left()
        if payload.license_type == "trial":
            # honour whichever deadline comes first: the issued key or the
            # trial counter, so the trial cannot be extended by re-saving.
            counter = self.trial_days_left()
            days = counter if days is None else min(days, counter)
        status.days_left = days
        if days is not None:
            if days < -GRACE_DAYS:
                status.expired = True
                status.blocked = True
                status.message = "Licence expir\u00e9e"
            elif days < 0:
                status.in_grace = True
                status.message = f"Licence expir\u00e9e - p\u00e9riode de gr\u00e2ce ({-days} jour(s))"
            elif days <= EXPIRY_WARNING_DAYS:
                status.expiring_soon = True
                status.message = f"La licence expire dans {days} jour(s)"
        return status

    def info(self) -> dict[str, Any]:
        status = self.status()
        data = asdict(status)
        data["label"] = status.label
        return data

    def renew(self, extra_days: int, secret: str | None = None) -> LicenseStatus:
        row = self._row()
        if not row or not row.get("payload"):
            return LicenseStatus(message="Aucune licence \u00e0 renouveler", blocked=True)
        payload_data = json.loads(row["payload"])
        known = {f.name for f in __import__("dataclasses").fields(LicensePayload)}
        payload = LicensePayload(**{k: v for k, v in payload_data.items() if k in known})
        base = datetime.now()
        if payload.expires_at:
            try:
                current = datetime.fromisoformat(payload.expires_at.replace(" ", "T"))
                base = max(base, current)
            except ValueError:
                pass
        payload.expires_at = (base + timedelta(days=extra_days)).date().isoformat()
        signature = _sign(payload, secret)
        self.save(payload, signature, compute_serial_key(payload, secret))
        return self.status()

    def has_feature(self, feature: str) -> bool:
        row = self._row()
        if not row or not row.get("is_active"):
            return False
        payload_data = json.loads(row.get("payload") or "{}")
        features = payload_data.get("features") or []
        return not features or feature in features
