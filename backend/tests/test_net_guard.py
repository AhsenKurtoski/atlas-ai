"""Test della protezione SSRF (app.core.net_guard)."""
from __future__ import annotations

import pytest

from app.core.net_guard import UnsafeURLError, validate_url


@pytest.fixture(autouse=True)
def _private_disallowed(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)


class TestValidateUrl:
    def test_blocca_loopback(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://127.0.0.1:8000/todos")

    def test_blocca_localhost(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://localhost:8000/")

    def test_blocca_rete_privata(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://10.1.2.3/segreto")

    def test_blocca_metadata_cloud(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://169.254.169.254/latest/meta-data")

    def test_blocca_ipv6_loopback(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://[::1]:8080/")

    def test_blocca_schema_non_http(self):
        with pytest.raises(UnsafeURLError):
            validate_url("file:///etc/passwd")

    def test_blocca_credenziali_incorporate(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://user:pass@8.8.8.8/")

    def test_consente_ip_pubblico(self):
        url = "http://8.8.8.8/"
        assert validate_url(url) == url

    def test_opt_in_per_risorse_locali(self, monkeypatch):
        monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "true")
        url = "http://127.0.0.1:8000/"
        assert validate_url(url) == url

    def test_blocca_url_vuoto(self):
        with pytest.raises(UnsafeURLError):
            validate_url("")
