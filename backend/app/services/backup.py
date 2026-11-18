"""
Backup automatici del database locale (`backend/_local_db`).

I dati della modalità locale vivono in file JSON: un file perso o troncato
significa perdere profili, todo, budget e promemoria. Questo modulo crea uno
zip datato in `backend/_backups` e ruota i backup vecchi, senza mai far
fallire l'app se il backup non riesce.

Uso tipico:
- all'avvio del backend (`main.py`, lifespan);
- dal job `backup_local_db` dello scheduler (ogni 6 ore);
- prima di modificare i PIN (`POST /profili/{slug}/pin`).

Ripristino manuale: scompattare lo zip scelto dentro `backend/_local_db`.
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core import database
from app.core.logging_config import get_logger

log = get_logger(__name__)

# Quanti backup conservare (uno ogni 6 ore ≈ 3 giorni di storico).
MAX_BACKUPS = 14
_PREFIX = "atlas-local-db-"
# File che non vanno archiviati: lock (non è un dato) e segreto di firma
# (un backup condiviso non deve permettere di forgiare token).
_EXCLUDED_NAMES = {".scheduler.lock", ".atlas_secret"}


def backups_dir(source: Optional[Path] = None) -> Path:
    """Cartella dei backup (accanto a `_local_db`, quindi `backend/_backups`)."""
    base = Path(source) if source else Path(database.LOCAL_DB_DIR)
    return base.parent / "_backups"


def backup_local_db(*, source: Optional[Path] = None, keep: int = MAX_BACKUPS) -> Optional[Path]:
    """Crea uno zip di `_local_db` e ruota i backup oltre `keep`.

    Ritorna il percorso dell'archivio creato, oppure None se la sorgente non
    esiste o la scrittura fallisce (l'errore viene solo loggato).
    """
    source_dir = Path(source) if source else Path(database.LOCAL_DB_DIR)
    if not source_dir.is_dir():
        log.warning("Backup saltato: %s non esiste", source_dir)
        return None

    target_dir = backups_dir(source_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = _new_archive_path(target_dir)
        files = [
            path
            for path in sorted(source_dir.rglob("*"))
            if path.is_file()
            and path.name not in _EXCLUDED_NAMES
            and "__pycache__" not in path.parts
        ]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, path.relative_to(source_dir).as_posix())
        _prune(target_dir, keep)
        log.info("Backup database locale: %s (%d file)", archive.name, len(files))
        return archive
    except (OSError, zipfile.BadZipFile) as exc:
        log.error("Backup database locale fallito: %s", exc)
        return None


def list_backups(source: Optional[Path] = None) -> list[Path]:
    """Backup presenti, dal più vecchio al più recente."""
    target_dir = backups_dir(source)
    if not target_dir.is_dir():
        return []
    return sorted(target_dir.glob(f"{_PREFIX}*.zip"))


def _new_archive_path(target_dir: Path) -> Path:
    """Percorso unico anche con più backup nello stesso secondo."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = target_dir / f"{_PREFIX}{stamp}.zip"
    counter = 1
    while archive.exists():
        archive = target_dir / f"{_PREFIX}{stamp}-{counter}.zip"
        counter += 1
    return archive


def _prune(target_dir: Path, keep: int) -> None:
    """Elimina i backup più vecchi mantenendo gli ultimi `keep`."""
    archives = sorted(target_dir.glob(f"{_PREFIX}*.zip"))
    eccedenti = archives[: max(0, len(archives) - max(1, keep))]
    for old in eccedenti:
        try:
            old.unlink()
        except OSError as exc:  # pragma: no cover - dipende dal filesystem
            log.warning("Impossibile eliminare il backup %s: %s", old.name, exc)
