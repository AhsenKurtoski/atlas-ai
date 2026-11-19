"""
Backup cifrati del database locale (`backend/_local_db`).

I dati della modalità locale vivono in file JSON: un file perso o troncato
significa perdere profili, todo, budget e promemoria. Questo modulo crea
un'archivio datato in `backend/_backups`, cifrato con AES (Fernet) e con la
rotazione dei backup vecchi, senza mai far fallire l'app se il backup non riesce.

La chiave deriva da `ATLAS_BACKUP_PASSWORD` (se impostata) oppure dal segreto
del server (`ATLAS_SECRET_KEY` / `_local_db/.atlas_secret`): un backup copiato
su una chiavetta USB non è leggibile senza quella chiave.

Uso tipico:
- all'avvio del backend (`main.py`, lifespan);
- dal job `backup_local_db` dello scheduler (ogni 6 ore);
- prima di modificare i PIN (`POST /profili/{slug}/pin`).

Ripristino: `python -m app.services.backup decrypt _backups/<file>.zip.enc`
produce lo zip, poi scompattarlo dentro `backend/_local_db`.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core import database
from app.core.logging_config import get_logger

log = get_logger(__name__)

# Quanti backup conservare (uno ogni 6 ore ≈ 3 giorni di storico).
MAX_BACKUPS = 14
_PREFIX = "atlas-local-db-"
_ENCRYPTED_SUFFIX = ".zip.enc"
# File che non vanno archiviati: lock (non è un dato) e segreto di firma
# (un backup condiviso non deve permettere di forgiare token).
_EXCLUDED_NAMES = {".scheduler.lock", ".atlas_secret"}
_KEY_SALT = b"atlas-backup-v1"


def backups_dir(source: Optional[Path] = None) -> Path:
    """Cartella dei backup (accanto a `_local_db`, quindi `backend/_backups`)."""
    base = Path(source) if source else Path(database.LOCAL_DB_DIR)
    return base.parent / "_backups"


def _key_material() -> bytes:
    """Password dei backup: env dedicata, poi segreto del server."""
    password = os.getenv("ATLAS_BACKUP_PASSWORD", "").strip()
    if password:
        return password.encode("utf-8")
    from app.core.security import _secret_key

    return _secret_key().encode("utf-8")


def _fernet() -> Fernet:
    """Fernet con chiave derivata via scrypt (deterministica per installazione)."""
    material = _key_material()
    kdf = Scrypt(salt=_KEY_SALT, length=32, n=2**14, r=8, p=1)
    key = base64.urlsafe_b64encode(kdf.derive(material))
    return Fernet(key)


def _encrypt_file(source: Path, target: Path) -> None:
    token = _fernet().encrypt(source.read_bytes())
    target.write_bytes(token)


def decrypt_backup(archive: Path, destination: Optional[Path] = None) -> Path:
    """Decifra un backup `.zip.enc` e ritorna il percorso dello zip leggibile."""
    archive = Path(archive)
    if archive.suffix != ".enc":
        raise ValueError(f"{archive.name} non è un backup cifrato (.zip.enc)")
    destination = Path(destination) if destination else archive.with_suffix("")
    try:
        plain = _fernet().decrypt(archive.read_bytes())
    except InvalidToken as exc:
        raise ValueError(
            "Chiave non valida: il backup è stato creato con un'altra password o un altro segreto."
        ) from exc
    destination.write_bytes(plain)
    return destination


def backup_local_db(
    *,
    source: Optional[Path] = None,
    keep: int = MAX_BACKUPS,
    encrypt: bool = True,
) -> Optional[Path]:
    """Crea un archivio di `_local_db` e ruota i backup oltre `keep`.

    Ritorna il percorso creato (`.zip.enc` se cifrato), oppure None se la
    sorgente non esiste o la scrittura fallisce (l'errore viene solo loggato).
    """
    source_dir = Path(source) if source else Path(database.LOCAL_DB_DIR)
    if not source_dir.is_dir():
        log.warning("Backup saltato: %s non esiste", source_dir)
        return None

    target_dir = backups_dir(source_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        files = [
            path
            for path in sorted(source_dir.rglob("*"))
            if path.is_file()
            and path.name not in _EXCLUDED_NAMES
            and "__pycache__" not in path.parts
        ]

        if encrypt:
            plain = target_dir / (_new_archive_stem(target_dir) + ".zip")
            _write_zip(plain, source_dir, files)
            archive = plain.with_name(plain.name + ".enc")
            try:
                _encrypt_file(plain, archive)
            finally:
                plain.unlink(missing_ok=True)
        else:
            archive = target_dir / (_new_archive_stem(target_dir) + ".zip")
            _write_zip(archive, source_dir, files)

        _prune(target_dir, keep)
        log.info("Backup database locale: %s (%d file)", archive.name, len(files))
        return archive
    except (OSError, zipfile.BadZipFile) as exc:
        log.error("Backup database locale fallito: %s", exc)
        return None


def _write_zip(archive: Path, source_dir: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(source_dir).as_posix())


def list_backups(source: Optional[Path] = None) -> list[Path]:
    """Backup presenti (cifrati e vecchi zip), dal più vecchio al più recente."""
    target_dir = backups_dir(source)
    if not target_dir.is_dir():
        return []
    return sorted(target_dir.glob(f"{_PREFIX}*"))


def _new_archive_stem(target_dir: Path) -> str:
    """Nome unico anche con più backup nello stesso secondo."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{_PREFIX}{stamp}"
    counter = 1
    while any(target_dir.glob(f"{stem}*")):
        stem = f"{_PREFIX}{stamp}-{counter}"
        counter += 1
    return stem


def _prune(target_dir: Path, keep: int) -> None:
    """Elimina i backup più vecchi mantenendo gli ultimi `keep`."""
    archives = sorted(target_dir.glob(f"{_PREFIX}*"))
    eccedenti = archives[: max(0, len(archives) - max(1, keep))]
    for old in eccedenti:
        try:
            old.unlink()
        except OSError as exc:  # pragma: no cover - dipende dal filesystem
            log.warning("Impossibile eliminare il backup %s: %s", old.name, exc)


def _checksum(path: Path) -> str:
    """SHA-256 del backup: utile per verificare una copia su un altro disco."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"list", "decrypt", "backup"}:
        print("Uso: python -m app.services.backup [list | backup | decrypt <file.zip.enc>]")
        return 2
    if argv[0] == "list":
        for path in list_backups():
            print(f"{path.name}  {path.stat().st_size} byte  sha256={_checksum(path)[:16]}…")
        return 0
    if argv[0] == "backup":
        archive = backup_local_db()
        print(archive if archive else "Backup non riuscito")
        return 0 if archive else 1
    if len(argv) < 2:
        print("Manca il file da decifrare.")
        return 2
    try:
        print(decrypt_backup(Path(argv[1])))
    except (OSError, ValueError) as exc:
        print(f"Errore: {exc}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - utilità da riga di comando
    raise SystemExit(_main(sys.argv[1:]))
