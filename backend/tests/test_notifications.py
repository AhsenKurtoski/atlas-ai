"""
Test del servizio notifiche: verificano che il codice parli davvero con
l'endpoint Expo Push (mock HTTP locale) e che gli errori siano riportati.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import notifiche
from app.core import database


class _ExpoHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received: list[dict] = []
    response_status = 200
    response_body: dict = {"data": [{"status": "ok", "id": "ticket-1"}]}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"[]"
        _ExpoHandler.received.append(json.loads(raw))
        payload = json.dumps(_ExpoHandler.response_body).encode()
        self.send_response(_ExpoHandler.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:
        return


@pytest.fixture
def expo_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ExpoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("EXPO_PUSH_URL", f"http://127.0.0.1:{server.server_address[1]}/push")
    _ExpoHandler.received.clear()
    _ExpoHandler.response_status = 200
    _ExpoHandler.response_body = {"data": [{"status": "ok", "id": "ticket-1"}]}
    yield server
    server.shutdown()
    server.server_close()


class TestExpoPush:
    def test_invia_push_con_token_expo(self, expo_server):
        assert notifiche.invia_push("ExponentPushToken[abc123]", "Titolo", "Messaggio") is True
        payload = _ExpoHandler.received[-1]
        message = payload[0]
        assert message["to"] == "ExponentPushToken[abc123]"
        assert "Titolo" in message["title"]
        assert message["body"] == "Messaggio"

    def test_invia_push_errore_server(self, expo_server):
        _ExpoHandler.response_status = 500
        assert notifiche.invia_push("ExponentPushToken[abc123]", "Titolo", "Messaggio") is False

    def test_invia_push_ticket_rifiutato(self, expo_server):
        _ExpoHandler.response_body = {"data": [{"status": "error", "message": "Qualcosa è andato storto"}]}
        assert notifiche.invia_push("ExponentPushToken[abc123]", "Titolo", "Messaggio") is False

    def test_dispositivo_non_registrato_disattiva_il_token(self, expo_server):
        token = "ExponentPushToken[dead-000000]"
        database._fb_save_push_token("fratello2", token, "Test", "android")
        _ExpoHandler.response_body = {
            "data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]
        }

        assert notifiche.invia_a_profilo("fratello2", "Titolo", "Messaggio") == 0

        attivi = database._fb_get_push_tokens("fratello2")
        assert all(row.get("token") != token for row in attivi)

    def test_token_non_expo_senza_firebase(self, expo_server):
        assert notifiche.invia_push("token-fcm-nativo", "Titolo", "Messaggio") is False

    def test_token_vuoto(self):
        assert notifiche.invia_push("", "Titolo", "Messaggio") is False

    def test_invia_a_profilo_con_token_registrato(self, expo_server):
        token = "ExponentPushToken[profilo-test]"
        assert database._fb_save_push_token("mamma", token, "Test", "ios") is True
        inviati = notifiche.invia_a_profilo("mamma", "Ciao", "Messaggio reale")
        assert inviati == 1
        message = _ExpoHandler.received[-1][0]
        assert message["to"] == token

    def test_invia_a_profilo_senza_dispositivi(self):
        assert notifiche.invia_a_profilo("profilo-senza-token", "Ciao", "Nessuno") == 0

    def test_token_inattivo_non_riceve(self, expo_server):
        token = "ExponentPushToken[disattivato]"
        database._fb_save_push_token("papa", token, "Test", "android")
        assert database._fb_deactivate_push_token(token) is True
        assert notifiche.invia_a_profilo("papa", "Ciao", "Non deve partire") == 0
