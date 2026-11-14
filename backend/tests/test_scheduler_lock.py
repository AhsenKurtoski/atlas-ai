"""Test del lock inter-processo che evita scheduler duplicati."""
from __future__ import annotations

from app.core.scheduler_lock import ProcessLock


class TestProcessLock:
    def test_un_solo_processo_ottiene_il_lock(self, tmp_path):
        first = ProcessLock(tmp_path / "scheduler.lock")
        second = ProcessLock(tmp_path / "scheduler.lock")

        assert first.acquire() is True
        try:
            assert second.acquire() is False
        finally:
            first.release()

        assert second.acquire() is True
        second.release()

    def test_rilascio_ripetuto_non_solleva(self, tmp_path):
        lock = ProcessLock(tmp_path / "scheduler.lock")
        assert lock.acquire() is True
        lock.release()
        lock.release()

    def test_riacquisizione_dopo_rilascio(self, tmp_path):
        lock = ProcessLock(tmp_path / "scheduler.lock")
        assert lock.acquire() is True
        lock.release()
        assert lock.acquire() is True
        lock.release()
