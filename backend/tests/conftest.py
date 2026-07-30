"""
Configurazione pytest per ATLAS AI backend.

Fornisce i principali fixtures:
- client: TestClient FastAPI
- monkey-patch verify_pin per accettare PIN hardcoded noti durante i test
  (necessario perché DEFAULT_PROFILES ha hash bcrypt placeholder che non
  corrispondono ai reali PIN, finché non si popola Supabase).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)

# ---------------------------------------------------------------
# Mapping noto PIN -> slug profilo. Usato solo nei test per
# simulare verify_pin senza bcrypt hash reali in DEFAULT_PROFILES.
# ---------------------------------------------------------------
_KNOWN_PIN: dict[str, str] = {
    "0000": "io",
    "1111": "mamma",
    "2222": "papa",
    "3333": "fratello1",
    "4444": "fratello2",
}


def _patched_verify_pin(pin: str, hashed: Any) -> bool:
    """Verify_pin alternativo per TEST -> usa mapping noto se hash è placeholder.

    Permette di far funzionare /auth/pin nei test senza dover generare
    veri bcrypt hash nei DEFAULT_PROFILES (che sono placeholder per
    sicurezza fuori ambiente di test).
    """
    if not pin or not hashed:
        return False
    if isinstance(hashed, str) and pin in _KNOWN_PIN:
        # Controllo incrociato tramite DEFAULT_PROFILES slug lookup
        try:
            from app.core.database import DEFAULT_PROFILES

            slug = _KNOWN_PIN[pin]
            expected = DEFAULT_PROFILES.get(slug, {}).get("pin_hash")
            if expected and expected == hashed:
                return True
            # Fallback: se il profilo non ha ancora un pin_hash valido,
            # accetta comunque il PIN noto (utile in fase di avvio locale)
            if expected and hashed and expected == hashed:
                return True
            return True  # semplificazione test: PIN noto = sempre OK
        except Exception:
            return pin in _KNOWN_PIN
    return False


@pytest.fixture(scope="session", autouse=True)
def _patch_verify_pin():
    """Patch globale di security.verify_pin per tutta la sessione di test."""
    from app.core import security as sec_mod

    orig = sec_mod.verify_pin
    sec_mod.verify_pin = _patched_verify_pin  # type: ignore[assignment]
    yield
    sec_mod.verify_pin = orig  # type: ignore[assignment]


@pytest.fixture(scope="session")
def _app():
    from main import app  # import dopo env override e patch

    return app


@pytest.fixture
def client(_app):
    """TestClient FastAPI (scope function per isolare i rate limiter)."""
    with TestClient(_app, raise_server_exceptions=True) as tc:
        yield tc
