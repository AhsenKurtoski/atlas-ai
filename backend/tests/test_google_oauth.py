"""
Test dell'integrazione Google (senza chiamate di rete).

Verificano che l'URL OAuth sia costruito correttamente, che lo `state` sia
firmato e verificabile, e che lo stato "non configurato" sia esplicito.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.core.database import get_setting, set_setting
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


class TestTokenCifrati:
    """I token OAuth non devono mai finire in chiaro nel database."""

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "access_token": "ya29-access-di-test",
                "refresh_token": "1//refresh-di-test",
                "expires_in": 3600,
                "scope": "gmail.readonly calendar.events",
            }

    def test_token_cifrati_a_riposo(self, google_env, monkeypatch):
        monkeypatch.setattr(google_oauth.requests, "post", lambda *a, **k: self._FakeResponse())
        monkeypatch.setattr(google_oauth, "_fetch_email", lambda token: "famiglia@example.com")

        assert google_oauth.exchange_code("codice", "http://localhost:8000") is True

        raw = get_setting("google.tokens", {})
        assert "enc" in raw, "il valore salvato deve essere cifrato"
        serialized = str(raw)
        assert "ya29-access-di-test" not in serialized
        assert "1//refresh-di-test" not in serialized

        tokens = google_oauth._stored_tokens()
        assert tokens["access_token"] == "ya29-access-di-test"
        assert tokens["refresh_token"] == "1//refresh-di-test"
        assert google_oauth.status()["connesso"] is True

    def test_token_legacy_in_chiaro_ancora_leggibili(self):
        set_setting("google.tokens", {"access_token": "vecchio", "refresh_token": "r", "expires_at": 0})
        assert google_oauth._stored_tokens()["access_token"] == "vecchio"

    def test_blob_corrotto_non_esplode(self):
        set_setting("google.tokens", {"enc": "non-un-token-fernet"})
        assert google_oauth._stored_tokens() == {}
        assert google_oauth.status()["connesso"] is False
