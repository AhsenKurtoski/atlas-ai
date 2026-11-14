"""
Test multi-utente: isolamento dei dati per profilo, ruoli e logout reale.

Verificano i requisiti di un prodotto multi-utente:
- ogni membro vede solo la propria memoria chat e i propri dispositivi push;
- solo l'amministratore gestisce i profili famiglia;
- il logout revoca davvero il token sul server.
"""
from __future__ import annotations

from app.core import database
from app.core.security import create_access_token


def _headers(slug: str, ttl: int = 3600) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(slug, ttl_seconds=ttl)}"}


class TestRuoliFamiglia:
    def test_membro_non_puo_creare_profili(self, client):
        response = client.post(
            "/profili",
            json={"nome": "Intruso", "pin": "9999"},
            headers=_headers("mamma"),
        )
        assert response.status_code == 403
        assert "amministratore" in response.json()["message"].lower()

    def test_membro_non_puo_eliminare_profili(self, client):
        response = client.delete("/profili/papa", headers=_headers("fratello1"))
        assert response.status_code == 403

    def test_admin_puo_creare_profilo(self, client):
        response = client.post(
            "/profili",
            json={"nome": "Zia", "pin": "4321", "livello_italiano": "A2"},
            headers=_headers("io"),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        slug = response.json()["data"]["slug"]
        client.delete(f"/profili/{slug}", headers=_headers("io"))


class TestIsolamentoDati:
    def test_memoria_chat_isolata_per_profilo(self):
        database.save_message("io", "user", "segreto-solo-io")
        database.save_message("mamma", "user", "segreto-solo-mamma")

        memoria_io = [row["content"] for row in database.get_user_memory("io", limit=100)]
        memoria_mamma = [row["content"] for row in database.get_user_memory("mamma", limit=100)]

        assert "segreto-solo-io" in memoria_io
        assert "segreto-solo-io" not in memoria_mamma
        assert "segreto-solo-mamma" in memoria_mamma
        assert "segreto-solo-mamma" not in memoria_io

    def test_dispositivi_push_isolati_per_profilo(self, client):
        token = "ExponentPushToken[isolamento-123456]"
        etichetta = "SoloIo-Dispositivo"
        registered = client.post(
            "/notifiche/registra",
            json={"token": token, "device": etichetta, "platform": "ios"},
            headers=_headers("io"),
        )
        assert registered.status_code == 200

        dispositivi_mamma = client.get(
            "/notifiche/dispositivi", headers=_headers("mamma")
        ).json()["data"]
        assert all(etichetta not in str(row) for row in dispositivi_mamma)

        dispositivi_io = client.get("/notifiche/dispositivi", headers=_headers("io")).json()["data"]
        assert any(row.get("platform") == "ios" for row in dispositivi_io)

        client.delete(f"/notifiche/registra?token={token}", headers=_headers("io"))


class TestLogoutReale:
    def test_logout_revoca_il_token(self, client):
        headers = _headers("mamma", ttl=600)
        assert client.get("/auth/me", headers=headers).status_code == 200

        logout = client.post("/auth/logout", headers=headers)
        assert logout.status_code == 200

        assert client.get("/auth/me", headers=headers).status_code == 401
        assert client.get("/todos", headers=headers).status_code == 401

    def test_token_non_revocato_continua_a_funzionare(self, client):
        headers = _headers("papa", ttl=600)
        assert client.get("/auth/me", headers=headers).status_code == 200
