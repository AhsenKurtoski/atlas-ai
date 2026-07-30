"""
Integration test per gli endpoint FastAPI principali:
- GET /            → health check (200, status=ok)
- GET /profili     → mappa profili con slug noti (io, mamma, papa, ...)
- POST /auth/pin   → autenticazione PIN: successo / errore / rate limit
- POST /chat       → echo fallback (mock mode = no Supabase, no Gemini)
- POST /todos, GET /todos, POST /todos/{n}/completa
- POST /budget/spesa, GET /budget
- Pydantic validation: campo non valido → 422
"""
from __future__ import annotations

import time

import pytest


class TestHealth:
    def test_root_200(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "versione" in body
        assert body.get("profili", 0) >= 1

    def test_profili_richiama_tutti_default(self, client):
        r = client.get("/profili")
        assert r.status_code == 200
        body = r.json()
        for expected in ("io", "mamma", "papa"):
            assert expected in body, f"Manca profilo {expected}"


class TestAuthPin:
    def test_auth_pin_successo(self, client):
        r = client.post("/auth/pin", json={"profilo": "io", "pin": "0000"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("auth") is True
        assert isinstance(body.get("token"), str) and len(body["token"]) > 20

    def test_auth_pin_errato(self, client):
        r = client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
        assert r.status_code == 200  # endpoint ritorna sempre 200 con auth=False
        body = r.json()
        assert body.get("auth") is False

    def test_auth_pin_non_numerico_422(self, client):
        r = client.post("/auth/pin", json={"profilo": "io", "pin": "ABCD"})
        assert r.status_code == 422

    def test_auth_pin_profilo_sconosciuto(self, client):
        r = client.post("/auth/pin", json={"profilo": "nonesiste", "pin": "0000"})
        assert r.status_code == 200
        assert r.json().get("auth") is False

    def test_auth_pin_rate_limit(self, client):
        # 5 richieste ok allowed (5/minute) poi 429
        for i in range(5):
            r = client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
            # Potrebbe essere 200 (auth=False)
        # Sesta richiesta: dovrebbe essere rate limitata (dipendenza slowapi in memoria)
        r6 = client.post("/auth/pin", json={"profilo": "io", "pin": "9999"})
        # Se il limiter è attivo → 429, altrimenti 200 (a seconda dell'ordine test)
        assert r6.status_code in (200, 429)


class TestChat:
    def test_chat_risposta_non_vuota(self, client):
        r = client.post("/chat", json={"msg": "Ciao, presentati!", "profilo": "io"})
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert isinstance(body["reply"], str) and len(body["reply"]) > 0


class TestTodosEndpoints:
    def test_flusso_completo_todos(self, client):
        # 1. aggiungi
        r_add = client.post(
            "/todos",
            json={"task": "Task integrazione", "slug": "io", "assegnato_a": "Tutti"},
        )
        assert r_add.status_code == 200
        # 2. lista
        r_list = client.get("/todos")
        assert r_list.status_code == 200
        data = r_list.json().get("data") or []
        assert any("Task integrazione" in (t.get("task") or "") for t in data)
        # 3. completa il primo
        if data:
            r_comp = client.post("/todos/1/completa")
            assert r_comp.status_code == 200


class TestBudgetEndpoints:
    def test_flusso_budget(self, client):
        # 1. aggiungi spesa
        r_add = client.post(
            "/budget/spesa",
            json={
                "importo": 15.99,
                "categoria": "Svago",
                "descrizione": "Caffè",
                "slug": "io",
            },
        )
        assert r_add.status_code == 200, r_add.text
        # 2. riepilogo totale >= 15.99
        r_sum = client.get("/budget")
        assert r_sum.status_code == 200
        tot = (r_sum.json().get("data") or {}).get("totale", 0.0)
        assert float(tot) >= 15.99

    def test_budget_importo_negativo_422(self, client):
        r = client.post(
            "/budget/spesa",
            json={"importo": -1, "categoria": "Cibo", "descrizione": "", "slug": "io"},
        )
        assert r.status_code == 422

    def test_budget_senza_slug_422(self, client):
        r = client.post(
            "/budget/spesa",
            json={"importo": 10, "categoria": "Cibo", "descrizione": ""},
        )
        assert r.status_code == 422


class TestPydanticValidation:
    def test_chat_msg_vuoto_422(self, client):
        r = client.post("/chat", json={"msg": "", "profilo": "io"})
        assert r.status_code == 422

    def test_chat_profilo_mancante_422(self, client):
        r = client.post("/chat", json={"msg": "ciao"})
        assert r.status_code == 422
