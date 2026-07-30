"""
Modulo logging strutturato per ATLAS AI v3.0
Fornisce logger coerenti con filtro di livello da env e formato leggibile.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOGGERS: dict[str, logging.Logger] = {}
_CONFIGURED = False


def _configure_root() -> None:
    """Configura il root logger una sola volta (lazy init)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    env = os.getenv("APP_ENV", "development")
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        if env == "production"
        else "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    handlers.append(stream)

    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        file = RotatingFileHandler(
            os.path.join(log_dir, "atlas.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file.setFormatter(formatter)
        handlers.append(file)
    except OSError:
        pass

    root = logging.getLogger()
    root.setLevel(level)
    # Svuota handler esistenti per evitare doppie stampe in caso di hot-reload
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("supabase").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """Restituisce un logger configurato.

    Args:
        name: Nome del logger (solitamente __name__ del modulo).
        level: Override opzionale del livello per questo specifico logger.
    """
    _configure_root()
    if name not in _LOGGERS:
        logger = logging.getLogger(name)
        if level is not None:
            logger.setLevel(level)
        _LOGGERS[name] = logger
    return _LOGGERS[name]
