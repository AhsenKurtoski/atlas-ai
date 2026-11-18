"""
Hardening dei PIN e del database locale.

Copre:
- fail closed in produzione quando `profiles.json` manca, è corrotto o parziale;
- blocco dei PIN demo in produzione (login e cambio PIN da admin);
- endpoint admin `POST /profili/{slug}/pin`;
- backup automatico di `_local_db` con rotazione;
- default CORS fail closed in produzione.

I test girano con `APP_ENV=test` (vedi conftest): il comportamento di produzione
viene simulato con monkeypatch, mai toccando i dati reali.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from app.core import database, settings
from app.services import backup


@pytest.fixture
def produzione(monkeypatch):
    """Simula APP_ENV=production nel layer database."""
    monkeypatch.setattr(database, "is_production", lambda: True)


# ---------------------------------------------------------------- fail closed
class TestProfiliFailClosed:
    def test_produzione_senza_file_nessun_profilo(self, produzione, tmp_path, monkeypatch):
        monkeypatch.setattr(database, "LOCAL_DB_DIR", tmp_path)
        assert database._local_profiles() == {}

    def test_produzione_file_corrotto_nessun_profilo(self, produzione, tmp_path, monkeypatch):
        monkeypatch.setattr(database, "LOCAL_DB_DIR", tmp_path)
        (tmp_path / "profiles.json").write_text("{ non-json", encoding="utf-8")
        assert database._local_profiles() == {}

    def test_produzione_file_parziale_non_aggiunge_demo(self, produzione, tmp_path, monkeypatch):
        monkeypatch.setattr(database, "LOCAL_DB_DIR", tmp_path)
        salvato = {"io": {"slug": "io", "nome": "Tu", "pin_hash": "$2b$12$abcdefghijklmnopqrstuv"}}
        (tmp_path / "profiles.json").write_text(json.dumps(salvato), encoding="utf-8")
        profili = database._local_profiles()
        assert set(profili) == {"io"}
        assert database.DEFAULT_PROFILES["io"]["pin_hash"] not in json.dumps(profili)

    def test_sviluppo_mantiene_i_profili_demo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(database, "LOCAL_DB_DIR", tmp_path)
        assert "io" in database._local_profiles()

    def test_riconoscimento_hash_demo(self):
        assert database.is_demo_pin_hash(database.DEFAULT_PROFILES["io"]["pin_hash"]) is True
        assert database.is_demo_pin_hash("$2b$12$altro-hash-qualsiasi") is False
        assert database.is_demo_pin_hash(None) is False


# ------------------------------------------------------------ PIN demo bloccati
class TestPinDemoBloccati:
    def test_login_demo_rifiutato_in_produzione(self, client, monkeypatch):
        import main

        monkeypatch.setattr(main, "is_production", lambda: True)
        risposta = client.post("/auth/pin", json={"profilo": "io", "pin": "0000"})
        assert risposta.status_code == 200
        corpo = risposta.json()
        assert corpo["auth"] is False
        assert "demo" in (corpo.get("message") or "").lower()

    def test_cambio_pin_verso_demo_rifiutato_in_produzione(self, client, auth_headers, monkeypatch):
        import main

        monkeypatch.setattr(main, "is_production", lambda: True)
        risposta = client.post("/profili/io/pin", headers=auth_headers, json={"pin": "1111"})
        assert risposta.status_code == 200
        corpo = risposta.json()
        assert corpo["status"] == "error"
        assert "demo" in (corpo.get("message") or "").lower()


# --------------------------------------------------------------- endpoint admin
class TestPinAdmin:
    def _crea_profilo(self, client, auth_headers, slug: str = "pinprova") -> str:
        risposta = client.post(
            "/profili",
            headers=auth_headers,
            json={"nome": "Pin Prova", "slug": slug, "pin": "1234"},
        )
        assert risposta.status_code == 200
        assert risposta.json()["status"] == "ok"
        return slug

    def test_cambia_pin_e_login(self, client, auth_headers):
        slug = self._crea_profilo(client, auth_headers)
        cambio = client.post(f"/profili/{slug}/pin", headers=auth_headers, json={"pin": "778899"})
        assert cambio.status_code == 200
        assert cambio.json()["status"] == "ok"
        assert "778899" not in cambio.text

        nuovo = client.post("/auth/pin", json={"profilo": slug, "pin": "778899"})
        assert nuovo.json()["auth"] is True
        vecchio = client.post("/auth/pin", json={"profilo": slug, "pin": "1234"})
        assert vecchio.json()["auth"] is False

    def test_cambio_pin_invalida_le_sessioni_del_profilo(self, client, auth_headers):
        slug = self._crea_profilo(client, auth_headers, slug="pinsess")
        sessione = client.post("/auth/pin", json={"profilo": slug, "pin": "1234"}).json()
        headers_profilo = {"Authorization": f"Bearer {sessione['token']}"}
        assert client.get("/auth/me", headers=headers_profilo).status_code == 200

        cambio = client.post(f"/profili/{slug}/pin", headers=auth_headers, json={"pin": "556677"})
        assert cambio.json()["status"] == "ok"
        assert "sessioni" in cambio.json()["message"].lower()

        revocata = client.get("/auth/me", headers=headers_profilo)
        assert revocata.status_code == 401
        assert "PIN aggiornato" in revocata.json()["message"]

        # Il token dell'amministratore resta valido: cambia solo il profilo toccato.
        assert client.get("/auth/me", headers=auth_headers).status_code == 200

        nuovo = client.post("/auth/pin", json={"profilo": slug, "pin": "556677"}).json()
        assert nuovo["auth"] is True
        assert (
            client.get("/auth/me", headers={"Authorization": f"Bearer {nuovo['token']}"}).status_code
            == 200
        )

    def test_pin_non_numerico_422(self, client, auth_headers):
        risposta = client.post("/profili/io/pin", headers=auth_headers, json={"pin": "abcd"})
        assert risposta.status_code == 422
        assert risposta.json().get("message")

    def test_profilo_sconosciuto(self, client, auth_headers):
        risposta = client.post("/profili/nessuno/pin", headers=auth_headers, json={"pin": "123456"})
        assert risposta.status_code == 200
        assert risposta.json()["status"] == "error"

    def test_solo_amministratore(self, client):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token('mamma')}"}
        risposta = client.post("/profili/io/pin", headers=headers, json={"pin": "123456"})
        assert risposta.status_code == 403

    def test_senza_token_401(self, client):
        risposta = client.post("/profili/io/pin", json={"pin": "123456"})
        assert risposta.status_code == 401


# ----------------------------------------------------------------------- backup
class TestBackupLocale:
    def test_crea_zip_con_i_dati(self, tmp_path):
        sorgente = tmp_path / "_local_db"
        sorgente.mkdir()
        (sorgente / "profiles.json").write_text("{}", encoding="utf-8")
        (sorgente / ".scheduler.lock").write_text("lock", encoding="utf-8")
        (sorgente / ".atlas_secret").write_text("segreto", encoding="utf-8")

        archivio = backup.backup_local_db(source=sorgente, keep=3)
        assert archivio is not None and archivio.exists()
        with zipfile.ZipFile(archivio) as zf:
            nomi = zf.namelist()
        assert "profiles.json" in nomi
        assert ".scheduler.lock" not in nomi
        # Il segreto di firma non deve uscire dal server con i backup.
        assert ".atlas_secret" not in nomi

    def test_rotazione_mantiene_gli_ultimi(self, tmp_path):
        sorgente = tmp_path / "_local_db"
        sorgente.mkdir()
        (sorgente / "profiles.json").write_text("{}", encoding="utf-8")
        for _ in range(5):
            assert backup.backup_local_db(source=sorgente, keep=2) is not None

        archivi = list((tmp_path / "_backups").glob("atlas-local-db-*.zip"))
        assert len(archivi) == 2
        assert len(backup.list_backups(source=sorgente)) == 2

    def test_sorgente_assente_ritorna_none(self, tmp_path):
        assert backup.backup_local_db(source=tmp_path / "mancante") is None


# ------------------------------------------------------------------------- CORS
class TestCors:
    def test_produzione_senza_origini_chiude(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        assert settings.cors_origins() == []

    def test_produzione_con_origini_esplicite(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example")
        assert settings.cors_origins() == ["https://app.example"]

    def test_sviluppo_resta_permissivo(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        assert settings.cors_origins() == ["*"]
