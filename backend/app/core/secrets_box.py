"""
Cifratura a riposo dei segreti dell'integrazione Google (token OAuth).

I token di accesso e di refresh permettono di leggere email e calendario: se
finiscono in chiaro in `_local_db` o in una tabella Supabase, chi legge quel
file ottiene l'account. Qui vengono sigillati con AES (Fernet) usando una
chiave derivata via scrypt dal segreto del server (`ATLAS_SECRET_KEY` o
`_local_db/.atlas_secret`), lo stesso materiale già usato per i backup.

Il formato salvato è `{"enc": "<token Fernet>"}`: un dizionario con i campi in
chiaro viene ancora letto (installazioni precedenti) e riscritto cifrato al
primo salvataggio. Se il segreto del server cambia i token non sono più
decifrabili: l'utente deve ricollegare Google, che è il comportamento sicuro.
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core.security import _secret_key

_SALT = b"atlas-oauth-v1"
_ENC_FIELD = "enc"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Fernet deterministico per installazione (scrypt una volta sola)."""
    kdf = Scrypt(salt=_SALT, length=32, n=2**14, r=8, p=1)
    key = base64.urlsafe_b64encode(kdf.derive(_secret_key().encode("utf-8")))
    return Fernet(key)


def seal(payload: dict[str, Any]) -> dict[str, str]:
    """Racchiude un dizionario in `{"enc": "..."}` pronto per il salvataggio."""
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return {_ENC_FIELD: _fernet().encrypt(blob.encode("utf-8")).decode("ascii")}


def unseal(stored: Any) -> dict[str, Any]:
    """Restituisce il dizionario originale, o `{}` se il blob non è valido."""
    if isinstance(stored, dict):
        blob = stored.get(_ENC_FIELD)
        if isinstance(blob, str) and blob:
            try:
                data = json.loads(_fernet().decrypt(blob.encode("ascii")))
            except (InvalidToken, ValueError, UnicodeDecodeError):
                return {}
            return data if isinstance(data, dict) else {}
        # Formato legacy in chiaro: lo accettiamo in lettura.
        return dict(stored)
    return {}


def is_sealed(stored: Any) -> bool:
    """True se il valore è già nel formato cifrato."""
    return isinstance(stored, dict) and isinstance(stored.get(_ENC_FIELD), str)
