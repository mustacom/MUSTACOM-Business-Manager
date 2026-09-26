"""Password hashing, input validation and defensive helpers.

Passwords are hashed with argon2id (memory-hard, the current OWASP
recommendation) and never stored or logged in clear text.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from typing import Any

try:  # argon2-cffi is a hard dependency of the shipped app
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32)
    _HASHER_NAME = "argon2id"
except Exception:  # pragma: no cover - fallback keeps dev machines running
    _HASHER = None
    _HASHER_NAME = "pbkdf2_sha256"

PBKDF2_ITERATIONS = 240_000

MIN_PASSWORD_LENGTH = 6
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9 +().\-]{6,32}$")
ICE_RE = re.compile(r"^[0-9]{15}$")


# ---------------------------------------------------------------------------
# password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    if not password:
        raise ValueError("empty password")
    if _HASHER is not None:
        return _HASHER.hash(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-effort verification; returns False for any malformed hash."""
    if not password or not stored_hash:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = stored_hash.split("$")
            expected = bytes.fromhex(digest_hex)
            computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                           bytes.fromhex(salt_hex), int(iterations))
            return hmac.compare_digest(expected, computed)
        except (ValueError, TypeError):
            return False
    if _HASHER is None:
        return False
    try:
        return _HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, Exception):
        return False


def needs_rehash(stored_hash: str) -> bool:
    if stored_hash.startswith("pbkdf2_sha256$"):
        return True
    if _HASHER is None:
        return False
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except Exception:
        return True


def hasher_name() -> str:
    return _HASHER_NAME


def generate_password(length: int = 12) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!?"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def password_strength(password: str) -> tuple[int, str]:
    """Return (score 0-4, label) for the password policy hint."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[a-z]", password) and re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"\d", password) or re.search(r"[^A-Za-z0-9]", password):
        score += 1
    labels = ["tr\u00e8s faible", "faible", "moyen", "fort", "tr\u00e8s fort"]
    return score, labels[min(score, 4)]


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
class ValidationError(ValueError):
    """Raised when user input fails validation."""

    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def clean_text(value: Any, max_length: int = 500) -> str:
    """Normalise and clamp a free text field."""
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\x00", "")
    text = unicodedata.normalize("NFC", text)
    return text.strip()[:max_length]


def require(value: Any, field: str, message: str = "champ obligatoire") -> str:
    text = clean_text(value)
    if not text:
        raise ValidationError(field, message)
    return text


def validate_username(username: str) -> str:
    text = clean_text(username, 32)
    if not USERNAME_RE.match(text):
        raise ValidationError("username",
                              "3 \u00e0 32 caract\u00e8res : lettres, chiffres, . _ -")
    return text


def validate_password(password: str, minimum: int = MIN_PASSWORD_LENGTH) -> str:
    if len(password) < minimum:
        raise ValidationError("password", f"minimum {minimum} caract\u00e8res")
    return password


def validate_email(email: str, required: bool = False) -> str:
    text = clean_text(email, 120)
    if not text:
        if required:
            raise ValidationError("email", "champ obligatoire")
        return ""
    if not EMAIL_RE.match(text):
        raise ValidationError("email", "adresse email invalide")
    return text


def validate_phone(phone: str, required: bool = False) -> str:
    text = clean_text(phone, 32)
    if not text:
        if required:
            raise ValidationError("phone", "champ obligatoire")
        return ""
    if not PHONE_RE.match(text):
        raise ValidationError("phone", "num\u00e9ro de t\u00e9l\u00e9phone invalide")
    return text


def validate_ice(ice: str) -> str:
    text = clean_text(ice, 20).replace(" ", "")
    if text and not ICE_RE.match(text):
        raise ValidationError("ice", "l'ICE marocain comporte 15 chiffres")
    return text


def validate_positive_number(value: Any, field: str, allow_zero: bool = True) -> float:
    try:
        number = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValidationError(field, "valeur num\u00e9rique invalide")
    if number < 0 or (not allow_zero and number == 0):
        raise ValidationError(field, "la valeur doit \u00eatre positive")
    return number


def validate_percent(value: Any, field: str, maximum: float = 100.0) -> float:
    number = validate_positive_number(value, field)
    if number > maximum:
        raise ValidationError(field, f"maximum {maximum:g}")
    return number


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def random_token(length: int = 32) -> str:
    return secrets.token_hex(length)
