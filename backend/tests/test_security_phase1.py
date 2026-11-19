"""Test del blocco sicurezza/privacy: recupero PIN, blocco progressivo, registro
accessi, revoca di tutte le sessioni, esportazione/cancellazione dati e backup
cifrati.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from app.core import auth_guard, database
from app.core.security import (
    generate_recovery_code,
    is_valid_recovery_code,
    normalize_recovery_code,
)


def _crea_profilo(client, auth_headers, nome="Test Recupero"):
    risposta = client.post(
        "/profili",
        json={"nome": nome, "pin": "2468", "livello_italiano": "B1"},
        headers=auth_headers,
    )
    assert risposta.status_code == 200
    body = risposta.json()
    assert body["status"] == "ok", body
    return body["data"]["slug"], body["data"]["codice_recupero"]


class TestCodiceRecupero:
    def test_codice_ha_formato_leggibile(self):
        codice = generate_recovery_code()
        assert is_valid_recovery_code(codice)
        assert len(codice.split("-")) == 4
        assert normalize_recovery_code(codice.lower().replace("-", " ")) == codice.replace("-", "")

    def test_recupero_reimposta_pin_e_consuma_il_codice(self, client, auth_headers):
        slug, codice = _crea_profilo(client, auth_headers)

        # Il vecchio PIN funziona, il codice è valido.
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["auth"] is True

        recupero = client.post(
            "/auth/recupero",
            json={"profilo": slug, "codice": codice, "nuovo_pin": "1357"},
        )
        assert recupero.status_code == 200
        body = recupero.json()
        assert body["auth"] is True
        assert body["token"]

        # Il token emesso dal recupero è già utilizzabile.
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
        assert me.status_code == 200

        # Nuovo PIN attivo, vecchio PIN no, codice monouso consumato.
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "1357"}).json()["auth"] is True
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["auth"] is False
        secondo = client.post(
            "/auth/recupero",
            json={"profilo": slug, "codice": codice, "nuovo_pin": "8642"},
        )
        assert secondo.status_code == 200
        assert secondo.json()["auth"] is False

    def test_solo_admin_genera_codici(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Admin")
        login = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()
        utente_headers = {"Authorization": f"Bearer {login['token']}"}

        negato = client.post(f"/profili/{slug}/recupero", headers=utente_headers)
        assert negato.status_code == 403

        creato = client.post(f"/profili/{slug}/recupero", headers=auth_headers)
        assert creato.status_code == 200
        nuovo_codice = creato.json()["data"]["codice_recupero"]
        assert is_valid_recovery_code(nuovo_codice)

        # Il codice generato funziona davvero.
        recupero = client.post(
            "/auth/recupero",
            json={"profilo": slug, "codice": nuovo_codice, "nuovo_pin": "9753"},
        )
        assert recupero.json()["auth"] is True

    def test_codice_errato_non_reimposta_il_pin(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Codice Errato")
        risposta = client.post(
            "/auth/recupero",
            json={"profilo": slug, "codice": "AAAA-BBBB-CCCC-DDDD", "nuovo_pin": "1357"},
        )
        assert risposta.status_code == 200
        assert risposta.json()["auth"] is False
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["auth"] is True


class TestBloccoProgressivo:
    def test_dopo_cinque_errori_il_profilo_e_bloccato(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Blocco")

        for _ in range(5):
            auth_guard.register_failure(slug)

        stato = auth_guard.lockout_status(slug)
        assert stato["locked"] is True
        assert stato["retry_after"] > 0

        # Anche il PIN corretto viene rifiutato finché il blocco è attivo.
        bloccato = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"})
        assert bloccato.status_code == 429
        assert "Troppi tentativi" in bloccato.json()["message"]

        # Scaduto il blocco (simulato), il PIN corretto torna ad funzionare.
        auth_guard.reset_all()
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["auth"] is True

    def test_blocco_cresce_con_gli_errori(self):
        auth_guard.reset_all()
        attese = []
        for _ in range(8):
            stato = auth_guard.register_failure("io")
            attese.append(stato["retry_after"])
        assert attese[:5] == [0, 0, 0, 0, 60]
        assert attese[5:] == [120, 300, 900]

    def test_accesso_riuscito_azzera_il_contatore(self, client):
        for _ in range(3):
            auth_guard.register_failure("io")
        assert client.post("/auth/pin", json={"profilo": "io", "pin": "0000"}).json()["auth"] is True
        assert auth_guard.lockout_status("io")["failures"] == 0


class TestRegistroAccessi:
    def test_login_e_errore_finiscono_nel_registro(self, client):
        client.post("/auth/pin", json={"profilo": "io", "pin": "0000"})
        client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})

        login = client.post("/auth/pin", json={"profilo": "io", "pin": "0000"}).json()
        headers = {"Authorization": f"Bearer {login['token']}"}
        eventi = client.get("/auth/accessi", headers=headers).json()["data"]

        motivi = {evento["motivo"] for evento in eventi}
        assert {"pin", "pin_errato"} <= motivi
        assert all(evento["profilo"] == "io" for evento in eventi)
        assert all(evento["quando"] for evento in eventi)
        assert all("dispositivo" in evento and "ip" in evento for evento in eventi)

    def test_eventi_oltre_la_retention_vengono_eliminati(self):
        auth_guard._write(
            auth_guard._LOG_FILE,
            [
                {"quando": "2020-01-01T00:00:00Z", "profilo": "io", "esito": "ok", "motivo": "pin"},
                {"quando": "2020-01-02T00:00:00Z", "profilo": "io", "esito": "ok", "motivo": "pin"},
            ],
        )
        auth_guard.record_event("io", "ok", "pin")
        eventi = auth_guard.list_events("io")
        assert len(eventi) == 1
        assert eventi[0]["quando"].startswith("20")
        assert not eventi[0]["quando"].startswith("2020")

    def test_un_membro_non_vede_il_registro_altrui(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Registro")
        login = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()
        headers = {"Authorization": f"Bearer {login['token']}"}

        negato = client.get("/auth/accessi?profilo=io", headers=headers)
        assert negato.status_code == 403

        # L'amministratore invece può consultare quello dei membri.
        assert client.get(f"/auth/accessi?profilo={slug}", headers=auth_headers).status_code == 200


class TestSessione:
    def test_esci_da_tutti_i_dispositivi_revoca_i_token(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Sessioni")
        primo = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["token"]
        secondo = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["token"]

        for token in (primo, secondo):
            assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        chiusura = client.post(
            "/auth/logout-tutti",
            headers={"Authorization": f"Bearer {primo}"},
        )
        assert chiusura.status_code == 200
        assert "Tutte le sessioni" in chiusura.json()["message"]

        for token in (primo, secondo):
            assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

        # Con il PIN si rientra normalmente.
        assert client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()["auth"] is True


class TestPrivacy:
    def test_informativa_pubblica(self, client):
        risposta = client.get("/privacy/informativa")
        assert risposta.status_code == 200
        data = risposta.json()["data"]
        assert data["sezioni"] and data["conservazione"]
        assert "backup" in data["conservazione"]

    def test_esporta_solo_i_propri_dati(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Export")
        login = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()
        headers = {"Authorization": f"Bearer {login['token']}"}

        client.post("/chat", json={"msg": "Ciao ATLAS"}, headers=headers)
        risposta = client.get("/privacy/dati", headers=headers)

        assert risposta.status_code == 200
        assert "attachment" in risposta.headers["content-disposition"]
        assert risposta.headers["cache-control"] == "no-store"
        body = risposta.json()
        assert body["profilo"]["slug"] == slug
        assert body["accessi"]
        testo = json.dumps(body)
        assert "pin_hash" not in testo
        assert "recovery_hash" not in testo

    def test_cancella_il_proprio_profilo(self, client, auth_headers):
        slug, _ = _crea_profilo(client, auth_headers, nome="Test Cancella")
        login = client.post("/auth/pin", json={"profilo": slug, "pin": "2468"}).json()
        headers = {"Authorization": f"Bearer {login['token']}"}

        cancellazione = client.delete("/privacy/profilo", headers=headers)
        assert cancellazione.status_code == 200
        assert cancellazione.json()["status"] == "ok"

        assert client.get("/auth/me", headers=headers).status_code == 401
        assert slug not in client.get("/profili").json()
        assert slug not in json.dumps(database._fallback_read("family_reminders", []))

    def test_amministratore_non_puo_cancellarsi(self, client, auth_headers):
        risposta = client.delete("/privacy/profilo", headers=auth_headers)
        assert risposta.status_code == 200
        assert risposta.json()["status"] == "error"
        assert "amministratore" in risposta.json()["message"].lower()


class TestBackupCifrati:
    def test_backup_cifrato_si_decifra_solo_con_la_chiave(self, tmp_path, monkeypatch):
        from app.services import backup

        sorgente = tmp_path / "_local_db"
        sorgente.mkdir()
        (sorgente / "profiles.json").write_text('{"io": {"nome": "Tu"}}', encoding="utf-8")
        monkeypatch.setenv("ATLAS_BACKUP_PASSWORD", "password-di-prova")
        monkeypatch.setattr(database, "LOCAL_DB_DIR", sorgente)

        archivio = backup.backup_local_db(source=sorgente)
        assert archivio is not None
        assert archivio.name.endswith(".zip.enc")
        assert b"PK" not in archivio.read_bytes()[:4]

        with pytest.raises(zipfile.BadZipFile):
            zipfile.ZipFile(archivio)

        chiaro = backup.decrypt_backup(archivio)
        with zipfile.ZipFile(chiaro) as zf:
            assert "profiles.json" in zf.namelist()
            assert json.loads(zf.read("profiles.json"))["io"]["nome"] == "Tu"

        # Con un'altra password il backup non si apre.
        monkeypatch.setenv("ATLAS_BACKUP_PASSWORD", "password-sbagliata")
        with pytest.raises(ValueError):
            backup.decrypt_backup(archivio, tmp_path / "altro.zip")

    def test_rotazione_mantiene_solo_i_backup_recenti(self, tmp_path, monkeypatch):
        from app.services import backup

        sorgente = tmp_path / "_local_db"
        sorgente.mkdir()
        (sorgente / "profiles.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("ATLAS_BACKUP_PASSWORD", "password-di-prova")
        monkeypatch.setattr(database, "LOCAL_DB_DIR", sorgente)

        for _ in range(4):
            assert backup.backup_local_db(source=sorgente, keep=2) is not None
        assert len(backup.list_backups(source=sorgente)) == 2
