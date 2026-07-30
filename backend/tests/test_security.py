"""
Unit test per il modulo sicurezza (app.core.security):
- hash_pin / verify_pin (bcrypt)
- is_safe_numeric_pin (validazione lunghezza e cifre)
- constant_time_equal (non timing-leak)
- generate_safe_token (entropia)
- sanitize_alphanum
- sha256_text
"""
from __future__ import annotations

import pytest

from app.core.security import (
    constant_time_equal,
    generate_safe_token,
    hash_pin,
    is_safe_numeric_pin,
    sanitize_alphanum,
    sha256_text,
    verify_pin,
)


class TestHashingPin:
    def test_hash_pin_restituisce_stringa_bcrypt(self):
        h = hash_pin("0000")
        assert isinstance(h, str)
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_hash_pin_pin_vuoto_raise(self):
        with pytest.raises(ValueError):
            hash_pin("")

    def test_verify_pin_corretto(self):
        h = hash_pin("1234")
        assert verify_pin("1234", h) is True

    def test_verify_pin_errato(self):
        h = hash_pin("1234")
        assert verify_pin("0000", h) is False
        assert verify_pin("", h) is False
        assert verify_pin("1234", "") is False

    def test_verify_pin_hash_malformato_non_raise(self):
        assert verify_pin("1234", "non-e-un-hash") is False


class TestValidazionePin:
    def test_is_safe_numeric_pin_valido(self):
        assert is_safe_numeric_pin("0000") is True
        assert is_safe_numeric_pin("12345678") is True

    def test_is_safe_numeric_pin_lunghezze_non_valide(self):
        assert is_safe_numeric_pin("123") is False  # troppo corto
        assert is_safe_numeric_pin("123456789") is False  # troppo lungo
        assert is_safe_numeric_pin("") is False

    def test_is_safe_numeric_pin_non_cifre(self):
        assert is_safe_numeric_pin("12a4") is False
        assert is_safe_numeric_pin("12-4") is False
        assert is_safe_numeric_pin(" 1234") is False


class TestConstantTime:
    def test_constant_time_equal_uguali(self):
        assert constant_time_equal("hello", "hello") is True
        assert constant_time_equal("", "") is True

    def test_constant_time_equal_diversi(self):
        assert constant_time_equal("hello", "world") is False
        assert constant_time_equal("a", "aa") is False


class TestToken:
    def test_generate_safe_token_length(self):
        t16 = generate_safe_token(16)
        assert len(t16) == 32  # 16 bytes = 32 hex
        t40 = generate_safe_token(40)
        assert len(t40) == 80

    def test_generate_safe_token_unici(self):
        a = generate_safe_token()
        b = generate_safe_token()
        assert a != b


class TestSanitize:
    def test_sanitize_alphanum_base(self):
        assert sanitize_alphanum("Hello@World_123") == "Hello@World_123"
        assert sanitize_alphanum("foo<script>bar</script>") == "fooscriptbarscript"

    def test_sanitize_alphanum_vuoto(self):
        assert sanitize_alphanum("") == ""


class TestSha256:
    def test_sha256_deterministico(self):
        assert sha256_text("abc") == sha256_text("abc")
        assert sha256_text("abc") != sha256_text("abd")

    def test_sha256_salt(self):
        assert sha256_text("abc", "salt1") != sha256_text("abc", "salt2")
