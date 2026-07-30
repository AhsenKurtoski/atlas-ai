"""
Modulo sicurezza di ATLAS AI v3.0
Fornisce hashing PIN/secret + rate limiting comune.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from passlib.context import CryptContext

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------- Hashing PIN / password ----------
def hash_pin(pin: str) -> str:
    """Hash sicuro di un PIN o password (bcrypt, adatto a 4+ cifre)."""
    if not pin:
        raise ValueError("PIN non può essere vuoto")
    return _pwd_ctx.hash(pin)


def verify_pin(pin: str, hashed: str) -> bool:
    """Verifica un PIN contro il suo hash bcrypt."""
    if not pin or not hashed:
        return False
    try:
        return _pwd_ctx.verify(pin, hashed)
    except Exception:
        return False


def constant_time_equal(a: str, b: str) -> bool:
    """Confronto a tempo costante per evitare timing attack."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------- Generazione token sicuri ----------
def generate_safe_token(length: int = 32) -> str:
    """Genera un token casuale URL-safe e crittograficamente sicuro."""
    return os.urandom(length).hex()


def sha256_text(text: str, salt: Optional[str] = None) -> str:
    """SHA256 opzionalmente saltato (utile per checksum / anonimizzazione)."""
    data = (salt or "") + text
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------- Validazione input ----------
def is_safe_numeric_pin(pin: str, min_len: int = 4, max_len: int = 8) -> bool:
    """Verifica che la stringa PIN sia composta solo da cifre con lunghezza ammessa."""
    if not pin:
        return False
    if not (min_len <= len(pin) <= max_len):
        return False
    return pin.isdigit()


def sanitize_alphanum(value: str, extra: str = "_-.@") -> str:
    """Rimuove tutti i caratteri NON alfanumerici o in `extra`."""
    if not value:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | set(extra)
    return "".join(ch for ch in value if ch in allowed)
