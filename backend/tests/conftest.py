"""
Configurazione pytest per ATLAS AI backend.

Fixture principali:
- `client`: TestClient FastAPI con lifespan attivo
- `auth_headers`: header Authorization con token firmato reale
- `_isolated_db`: sposta i file locale in una cartella temporanea (nessun
  dato di sviluppo viene toccato dai test)

I test usano i veri hash bcrypt dei PIN demo: nessun monkey-patch di
`verify_pin`, così l'autenticazione viene provata davvero.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
os.environ.pop("GOOGLE_API_KEY_1", None)
os.environ.pop("GEMINI_KEY_1", None)


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    """Isola il database locale dei test in una directory temporanea."""
    from app.core import database

    temp_dir = tmp_path_factory.mktemp("local_db")
    original = database.LOCAL_DB_DIR
    database.LOCAL_DB_DIR = temp_dir
    yield temp_dir
    database.LOCAL_DB_DIR = original


@pytest.fixture(scope="session")
def _app():
    from main import app

    return app


@pytest.fixture(scope="session")
def _limiter():
    from main import limiter

    return limiter


@pytest.fixture(scope="session")
def auth_token() -> str:
    from app.core.security import create_access_token

    return create_access_token("io")


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def client(_app):
    """TestClient FastAPI (nuovo contesto per isolare lifespan e stato)."""
    with TestClient(_app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_rate_limiter(_limiter):
    """Evita che i test si influenzino a vicenda sul rate limiting."""
    try:
        _limiter.reset()
    except Exception:
        pass
    yield
