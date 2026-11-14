"""
Lock inter-processo per lo scheduler.

Con più worker (gunicorn/uvicorn --workers N) ogni processo avvierebbe gli
stessi job: notifiche duplicate ogni giorno. Il lock su file garantisce che
solo un processo per host esegua lo scheduler; gli altri restano attivi per
le API. Su più host serve un solo processo dedicato allo scheduler.

Implementazione cross-platform: ``fcntl.flock`` su POSIX, ``msvcrt.locking``
su Windows. Il lock è rilasciato dall'OS anche se il processo termina.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # POSIX
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class ProcessLock:
    """Lock esclusivo non bloccante su un file."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.touch()
            handle = open(self.path, "r+b")
        except OSError:
            return False

        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - piattaforma senza lock supportato
                handle.close()
                return False
        except OSError:
            handle.close()
            return False

        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            handle.close()

    def __enter__(self) -> "ProcessLock":
        if not self.acquire():
            raise RuntimeError(f"Lock già acquisito: {self.path}")
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()


__all__ = ["ProcessLock"]
