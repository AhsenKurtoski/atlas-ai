"""
Integration test per gli endpoint FastAPI.

Copre: health, profili, auth (PIN reale), chat, todos, budget, dashboard,
notifiche, impostazioni, italiano e integrazione Google (stato).
"""
from __future__ import annotations

import base64


class TestHealth:
    def test_root_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "ok"
        assert body.get("versione") == "3.1.0"
        assert body.get("profili", 0) >= 5
        assert body.get("db_mode") in ("locale", "supabase")
        assert isinstance(body.get("llm"), bool)

    def test_profili_ritorna_slug_noti(self, client):
        response = client.get("/profili")
        assert response.status_code == 200
        body = response.json()
        for expected in ("io", "mamma", "papa"):
            assert expected in body
        # I dati sensibili non devono uscire
        assert all("pin_hash" not in profile for profile in body.values())


class TestAuthPin:
    def test_auth_pin_successo(self, client):
        response = client.post("/auth/pin", json={"profilo": "io", "pin": "0000"})
        assert response.status_code == 200
        body = response.json()
        assert body.get("auth") is True
        assert body.get("slug") == "io"
        assert isinstance(body.get("token"), str) and len(body["token"]) > 30
        assert body.get("expires_in", 0) > 0

    def test_auth_pin_mamma_reale(self, client):
        response = client.post("/auth/pin", json={"profilo": "mamma", "pin": "1111"})
        assert response.status_code == 200
        assert response.json().get("auth") is True

    def test_auth_pin_errato(self, client):
        response = client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
        assert response.status_code == 200
        assert response.json().get("auth") is False

    def test_auth_pin_non_numerico_422(self, client):
        response = client.post("/auth/pin", json={"profilo": "io", "pin": "ABCD"})
        assert response.status_code == 422
        assert response.json().get("message")

    def test_auth_pin_profilo_sconosciuto(self, client):
        response = client.post("/auth/pin", json={"profilo": "nonesiste", "pin": "0000"})
        assert response.status_code == 200
        assert response.json().get("auth") is False

    def test_auth_pin_rate_limit(self, client):
        for _ in range(5):
            client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
        response = client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
        assert response.status_code == 429

    def test_auth_me_con_token(self, client, auth_headers):
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body.get("slug") == "io"
        assert body.get("livello_italiano")

    def test_auth_me_senza_token(self, client):
        assert client.get("/auth/me").status_code == 401


class TestProtezioneEndpoint:
    def test_todos_senza_token_401(self, client):
        assert client.get("/todos").status_code == 401

    def test_budget_senza_token_401(self, client):
        assert client.get("/budget").status_code == 401

    def test_chat_senza_token_401(self, client):
        assert client.post("/chat", json={"msg": "ciao"}).status_code == 401

    def test_token_falsificato_401(self, client):
        headers = {"Authorization": "Bearer abc.def"}
        assert client.get("/todos", headers=headers).status_code == 401


class TestChat:
    def test_chat_senza_chiavi_risponde_con_avviso(self, client, auth_headers):
        response = client.post("/chat", json={"msg": "Ciao ATLAS"}, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "reply" in body and len(body["reply"]) > 0
        assert body.get("latency_ms") is not None

    def test_trascrizione_audio_non_valido(self, client, auth_headers):
        response = client.post(
            "/chat/trascrivi",
            json={"audio_base64": base64.b64encode(b"x" * 600).decode(), "mime_type": "audio/mp4"},
            headers=auth_headers,
        )
        # Senza chiavi Gemini il servizio risponde 503 (non finge una trascrizione)
        assert response.status_code == 503

    def test_trascrizione_mime_errato_400(self, client, auth_headers):
        response = client.post(
            "/chat/trascrivi",
            json={"audio_base64": base64.b64encode(b"x" * 600).decode(), "mime_type": "text/plain"},
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestTodosEndpoints:
    def test_flusso_completo_todos(self, client, auth_headers):
        response_add = client.post(
            "/todos",
            json={"task": "Task integrazione", "assegnato_a": "Tutti"},
            headers=auth_headers,
        )
        assert response_add.status_code == 200

        response_list = client.get("/todos", headers=auth_headers)
        assert response_list.status_code == 200
        data = response_list.json().get("data") or []
        assert any("Task integrazione" in (todo.get("task") or "") for todo in data)

        index = next(
            i for i, todo in enumerate(data, 1) if "Task integrazione" in (todo.get("task") or "")
        )
        response_done = client.post(f"/todos/{index}/completa", headers=auth_headers)
        assert response_done.status_code == 200
        assert response_done.json().get("status") == "ok"

    def test_completa_indice_non_valido(self, client, auth_headers):
        response = client.post("/todos/9999/completa", headers=auth_headers)
        assert response.status_code == 200
        assert response.json().get("status") == "error"

    def test_filtro_pending(self, client, auth_headers):
        response = client.get("/todos?filtro=pending", headers=auth_headers)
        assert response.status_code == 200
        assert all(todo.get("done") is False for todo in response.json().get("data") or [])


class TestBudgetEndpoints:
    def test_flusso_budget(self, client, auth_headers):
        response_add = client.post(
            "/budget/spesa",
            json={"importo": 15.99, "categoria": "Svago", "descrizione": "Caffè"},
            headers=auth_headers,
        )
        assert response_add.status_code == 200, response_add.text

        response_sum = client.get("/budget", headers=auth_headers)
        assert response_sum.status_code == 200
        total = (response_sum.json().get("data") or {}).get("totale", 0.0)
        assert float(total) >= 15.99

    def test_budget_importo_negativo_422(self, client, auth_headers):
        response = client.post(
            "/budget/spesa",
            json={"importo": -1, "categoria": "Cibo", "descrizione": ""},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json().get("message")

    def test_budget_senza_categoria_422(self, client, auth_headers):
        response = client.post(
            "/budget/spesa",
            json={"importo": 10, "descrizione": "x"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestDashboard:
    def test_dashboard_reale(self, client, auth_headers):
        response = client.get("/dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json().get("data") or {}
        for key in ("todos_pendenti", "spesa_mese", "dispositivi_notifiche", "punti_italiano"):
            assert key in data


class TestNotifiche:
    def test_registra_token_e_lista(self, client, auth_headers):
        token = "ExponentPushToken[test-token-123456]"
        response = client.post(
            "/notifiche/registra",
            json={"token": token, "device": "Test", "platform": "android"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

        devices = client.get("/notifiche/dispositivi", headers=auth_headers)
        assert devices.status_code == 200
        assert len(devices.json().get("data") or []) >= 1

        removed = client.delete(f"/notifiche/registra?token={token}", headers=auth_headers)
        assert removed.status_code == 200

    def test_token_non_valido(self, client, auth_headers):
        response = client.post(
            "/notifiche/registra",
            json={"token": "abc", "device": "", "platform": ""},
            headers=auth_headers,
        )
        assert response.status_code == 422  # min_length=8 su token


class TestImpostazioni:
    def test_lettura_e_scrittura(self, client, auth_headers):
        response = client.get("/impostazioni", headers=auth_headers)
        assert response.status_code == 200
        data = response.json().get("data") or {}
        assert "automazioni" in data and "notifiche" in data

        update = client.post(
            "/impostazioni",
            json={"automazioni": {"promemoria_acqua": False}},
            headers=auth_headers,
        )
        assert update.status_code == 200
        assert update.json()["data"]["automazioni"]["promemoria_acqua"] is False
        # Il resto delle automazioni resta invariato
        assert update.json()["data"]["automazioni"]["briefing_giornaliero"] is True


class TestItaliano:
    def test_lezione(self, client, auth_headers):
        response = client.get("/italiano/lezione?livello=B1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json().get("data") or {}
        assert data["lezione"]["livello"] == "B1"
        assert data["lezione"]["titolo"]
        assert "progresso" in data

    def test_quiz_senza_soluzioni(self, client, auth_headers):
        response = client.get("/italiano/quiz?livello=A2&n=3", headers=auth_headers)
        assert response.status_code == 200
        domande = response.json()["data"]["domande"]
        assert len(domande) == 3
        assert all("risposta" not in domanda for domanda in domande)
        assert all(len(domanda["opzioni"]) == 4 for domanda in domande)

    def test_valutazione_quiz(self, client, auth_headers):
        quiz = client.get("/italiano/quiz?livello=A1&n=2", headers=auth_headers).json()["data"]["domande"]
        risposte = [{"id": domanda["id"], "scelta": 0} for domanda in quiz]
        response = client.post(
            "/italiano/quiz/valuta",
            json={"risposte": risposte, "livello": "A1"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["totale"] == 2
        assert data["punteggio"] >= 0
        assert "progresso" in data

    def test_progressi(self, client, auth_headers):
        response = client.get("/italiano/progressi", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "mio" in data and "classifica" in data


class TestProfili:
    def test_crea_e_elimina_profilo(self, client, auth_headers):
        created = client.post(
            "/profili",
            json={"nome": "Nonna", "pin": "5678", "livello_italiano": "A1"},
            headers=auth_headers,
        )
        assert created.status_code == 200
        assert created.json()["status"] == "ok"
        slug = created.json()["data"]["slug"]

        login = client.post("/auth/pin", json={"profilo": slug, "pin": "5678"})
        assert login.json().get("auth") is True

        deleted = client.delete(f"/profili/{slug}", headers=auth_headers)
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "ok"

    def test_non_eliminare_se_stessi(self, client, auth_headers):
        response = client.delete("/profili/io", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "error"


class TestGoogleIntegration:
    def test_stato_non_configurato(self, client, auth_headers):
        response = client.get("/integrazioni/google/stato", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["configurato"] is False
        assert data["connesso"] is False
        assert data["istruzioni"]

    def test_url_senza_configurazione(self, client, auth_headers):
        response = client.get("/integrazioni/google/url", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "error"


class TestAutomazioni:
    def test_elenco_automazioni(self, client, auth_headers):
        response = client.get("/automazioni", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json().get("data"), list)
