"""
Modulo sicurezza di ATLAS AI v3.0.

Fornisce:
- hashing PIN con bcrypt (`hash_pin` / `verify_pin`)
- confronto a tempo costante
- token di sessione firmati HMAC (stateless → funzionano con più worker)
- validazione input e sanitizzazione
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

import bcrypt

_BCRYPT_ROUNDS = 12

_SECRET_CACHE: Optional[str] = None
_SECRET_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "_local_db",
    ".atlas_secret",
)


# ---------- Hashing PIN / password ----------
def hash_pin(pin: str) -> str:
    """Hash bcrypt di un PIN (12 rounds, salt casuale)."""
    if not pin:
        raise ValueError("PIN non può essere vuoto")
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def verify_pin(pin: str, hashed: str) -> bool:
    """Verifica un PIN contro il suo hash bcrypt (False se hash malformato)."""
    if not pin or not hashed:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def constant_time_equal(a: str, b: str) -> bool:
    """Confronto a tempo costante per evitare timing attack."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------- Generazione token sicuri ----------
def generate_safe_token(length: int = 32) -> str:
    """Genera un token casuale esadecimale crittograficamente sicuro."""
    return os.urandom(length).hex()


def sha256_text(text: str, salt: Optional[str] = None) -> str:
    """SHA256 opzionalmente saltato (utile per checksum / anonimizzazione)."""
    data = (salt or "") + text
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------- Validazione input ----------
def is_safe_numeric_pin(pin: str, min_len: int = 4, max_len: int = 8) -> bool:
    """True solo se il PIN è composto da cifre con lunghezza ammessa."""
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


def normalize_slug(value: str) -> str:
    """Normalizza uno slug profilo (lowercase, solo lettere/cifre/underscore)."""
    cleaned = sanitize_alphanum((value or "").strip().lower(), extra="_-")
    return cleaned[:50]


# ---------- Token di sessione (HMAC, stateless) ----------
def _secret_key() -> str:
    """Segreto stabile: env ATLAS_SECRET_KEY oppure file locale generato una volta."""
    global _SECRET_CACHE
    if _SECRET_CACHE:
        return _SECRET_CACHE

    env_secret = os.getenv("ATLAS_SECRET_KEY", "").strip()
    if env_secret:
        _SECRET_CACHE = env_secret
        return _SECRET_CACHE

    try:
        os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
        if os.path.exists(_SECRET_FILE):
            with open(_SECRET_FILE, "r", encoding="utf-8") as handle:
                stored = handle.read().strip()
            if stored:
                _SECRET_CACHE = stored
                return stored
        generated = secrets.token_urlsafe(48)
        with open(_SECRET_FILE, "w", encoding="utf-8") as handle:
            handle.write(generated)
        try:
            os.chmod(_SECRET_FILE, 0o600)
        except OSError:
            pass
        _SECRET_CACHE = generated
        return generated
    except OSError:
        # Ultima risorsa: segreto in memoria (i token decadono al riavvio).
        _SECRET_CACHE = secrets.token_urlsafe(48)
        return _SECRET_CACHE


def token_ttl_seconds() -> int:
    """Durata sessione (default 8 ore, configurabile con TOKEN_TTL_HOURS)."""
    try:
        hours = float(os.getenv("TOKEN_TTL_HOURS", "8").replace(",", "."))
    except ValueError:
        hours = 8.0
    return int(max(1.0, min(hours, 24 * 30)) * 3600)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: str) -> str:
    return hmac.new(_secret_key().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def create_access_token(
    profile_slug: str,
    ttl_seconds: Optional[int] = None,
    pin_version: int = 0,
) -> str:
    """Crea un token `<payload>.<firma>` con scadenza (HMAC-SHA256).

    `pin_version` lega la sessione alla versione del PIN del profilo: quando
    l'amministratore cambia il PIN, la versione avanza e i token emessi prima
    diventano invalidi (revoca immediata delle sessioni di quel profilo).
    """
    if not profile_slug:
        raise ValueError("Slug profilo obbligatorio per creare un token")
    expires_at = int(time.time()) + int(ttl_seconds or token_ttl_seconds())
    version = max(0, int(pin_version))
    payload = _b64encode(f"{profile_slug}:{expires_at}:{version}".encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def decode_token_details(token: str) -> Optional[tuple[str, int, int]]:
    """Ritorna (slug, expires_at, pin_version) se il token è valido.

    I token emessi prima dell'introduzione di `pin_version` hanno due campi:
    vengono letti con versione 0, così restano validi finché il PIN non cambia.
    """
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not payload or not signature:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        raw = _b64decode(payload).decode("utf-8")
        parts = raw.rsplit(":", 2)
        if len(parts) == 3:
            slug, expires_raw, version_raw = parts
            version = int(version_raw)
        else:
            slug, expires_raw = parts
            version = 0
        expires_at = int(expires_raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not slug or expires_at < int(time.time()):
        return None
    return slug, expires_at, max(0, version)


def decode_access_token(token: str) -> Optional[str]:
    """Ritorna lo slug del profilo se il token è valido e non scaduto, altrimenti None."""
    details = decode_token_details(token)
    return details[0] if details else None


def token_info(token: str) -> Optional[tuple[str, int]]:
    """Ritorna (slug, expires_at) se valido, altrimenti None."""
    details = decode_token_details(token)
    return (details[0], details[1]) if details else None
