"""
Protezione SSRF per le richieste HTTP in uscita (fetch web / lettura pagine).

Gli strumenti AI possono scaricare URL arbitrari scelti dall'utente: senza
controlli un membro della famiglia potrebbe far leggere al server servizi
interni (``http://127.0.0.1:8000``, ``http://169.254.169.254``, NAS di casa).
Qui validiamo schema, host e IP risolti, seguendo i redirect manualmente.

Per abilitare esplicitamente risorse di rete locale (es. un servizio self-hosted)
imposta ``ALLOW_PRIVATE_FETCH=true`` nel backend/.env.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any, Mapping, Optional
from urllib.parse import urljoin, urlparse

import requests

from app.core.settings import env_bool

_DEFAULT_TIMEOUT = 15
_MAX_REDIRECTS = 3


class UnsafeURLError(ValueError):
    """URL non consentito (schema, credenziali o destinazione privata)."""


def allow_private_fetch() -> bool:
    return env_bool("ALLOW_PRIVATE_FETCH", default=False)


def validate_url(url: str) -> str:
    """Valida uno URL per l'uso server-side. Ritorna lo URL invariato."""
    if not url or not url.strip():
        raise UnsafeURLError("URL vuoto.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Sono consentiti solo URL http:// o https://.")
    if not parsed.hostname:
        raise UnsafeURLError("URL senza host.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL con credenziali incorporate non consentito.")
    if allow_private_fetch():
        return url

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                parsed.hostname, port, type=socket.SOCK_STREAM
            )
        }
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise UnsafeURLError(f"Host non risolvibile: {parsed.hostname}.") from exc

    if not addresses:
        raise UnsafeURLError(f"Host non risolvibile: {parsed.hostname}.")

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError as exc:
            raise UnsafeURLError(f"Indirizzo non valido: {address}.") from exc
        if not ip.is_global:
            raise UnsafeURLError(
                "Destinazione privata o riservata non consentita "
                f"({parsed.hostname} → {address})."
            )
    return url


def safe_get(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = _DEFAULT_TIMEOUT,
    params: Optional[dict[str, Any]] = None,
) -> requests.Response:
    """GET con validazione SSRF a ogni redirect (max 3)."""
    current = validate_url(url)
    for attempt in range(_MAX_REDIRECTS + 1):
        response = requests.get(
            current,
            headers=dict(headers or {}),
            params=params if attempt == 0 else None,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.is_redirect:
            location = response.headers.get("Location", "")
            if not location:
                return response
            current = validate_url(urljoin(current, location))
            continue
        return response
    raise UnsafeURLError("Troppi redirect: richiesta interrotta per sicurezza.")


__all__ = ["UnsafeURLError", "allow_private_fetch", "validate_url", "safe_get"]
