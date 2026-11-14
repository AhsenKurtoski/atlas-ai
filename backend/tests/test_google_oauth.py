"""
Test dell'integrazione Google (senza chiamate di rete).

Verificano che l'URL OAuth sia costruito correttamente, che lo `state` sia
firmato e verificabile, e che lo stato "non configurato" sia esplicito.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import google_oauth


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id-di-test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret-di-test")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/integrazioni/google/callback")
    return monkeypatch


class TestGoogleOAuth:
    def test_non_configurato(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        stato = google_oauth.status()
        assert stato["configurato"] is False
        assert stato["connesso"] is False
        assert "GOOGLE_CLIENT_ID" in stato["istruzioni"]
        with pytest.raises(RuntimeError):
            google_oauth.build_auth_url()

    def test_url_di_autorizzazione(self, google_env):
        url = google_oauth.build_auth_url("http://localhost:8000")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        assert parsed.netloc == "accounts.google.com"
        assert params["client_id"] == ["client-id-di-test"]
        assert params["response_type"] == ["code"]
        assert params["access_type"] == ["offline"]
        assert "gmail.readonly" in params["scope"][0]
        assert "calendar.events" in params["scope"][0]
        assert params["state"][0]

    def test_state_firmato_e_verificabile(self, google_env):
        url = google_oauth.build_auth_url("http://localhost:8000")
        state = parse_qs(urlparse(url).query)["state"][0]
        assert google_oauth.validate_state(state) is True
        assert google_oauth.validate_state(state + "manomesso") is False
        assert google_oauth.validate_state("") is False

    def test_redirect_uri_configurato(self, google_env):
        assert (
            google_oauth.default_redirect_uri("http://ignorato")
            == "http://localhost:8000/integrazioni/google/callback"
        )

    def test_redirect_uri_default_da_base_url(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
        assert (
            google_oauth.default_redirect_uri("http://192.168.1.10:8000/")
            == "http://192.168.1.10:8000/integrazioni/google/callback"
        )

    def test_disconnect_pulisce_i_token(self):
        google_oauth.disconnect()
        stato = google_oauth.status()
        assert stato["connesso"] is False
        assert stato["email"] == ""
