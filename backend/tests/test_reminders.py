"""Test reali di promemoria: parser, persistenza, API e scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core import context, database
from app.tools.family import (
    _parse_quando,
    annulla_promemoria,
    crea_promemoria,
    elenca_promemoria,
)

ROME = ZoneInfo("Europe/Rome")


def _now() -> datetime:
    return datetime(2026, 11, 16, 15, 30, tzinfo=ROME)


class TestParserPromemoria:
    def test_verso_le_4_5_sceglie_le_16(self):
        _, local, _ = _parse_quando("verso le 4-5 devo andare da Lidl", now=_now())
        assert local.hour == 16 and local.minute == 0
        assert local.date() == _now().date()

    def test_intervallo_in_corso_sceglie_la_fine(self):
        now = datetime(2026, 11, 16, 16, 30, tzinfo=ROME)
        _, local, _ = _parse_quando("verso le 4-5", now=now)
        # Dentro la finestra diamo 15 minuti di preavviso, arrotondati a 5 minuti.
        assert (local.hour, local.minute) == (16, 45)

    def test_intervallo_passato_va_a_domani(self):
        now = datetime(2026, 11, 16, 17, 30, tzinfo=ROME)
        _, local, _ = _parse_quando("verso le 4-5", now=now)
        assert local.date() == now.date() + timedelta(days=1)
        assert local.hour == 16

    def test_domani_alle_9(self):
        _, local, etichetta = _parse_quando("domani alle 9", now=_now())
        assert local.hour == 9 and local.date() == _now().date() + timedelta(days=1)
        assert "domani" in etichetta.lower()

    def test_tra_30_minuti(self):
        _, local, _ = _parse_quando("tra 30 minuti", now=_now())
        assert local == _now() + timedelta(minutes=30)

    def test_iso_con_fuso(self):
        _, local, _ = _parse_quando("2026-11-17T09:00:00+01:00", now=_now())
        assert local.hour == 9 and local.date().isoformat() == "2026-11-17"

    def test_orario_non_riconosciuto(self):
        with pytest.raises(ValueError):
            _parse_quando("quando ti pare", now=_now())


class TestPromemoriaLocale:
    def setup_method(self):
        database._fallback_write("family_reminders", [])
        database._fallback_write("family_todos", [])

    def test_crea_promemoria_con_lista(self):
        database._fb_add_todo("Latte", "io")
        database._fb_add_todo("Pane", "io")
        token = context.current_profile.set("mamma")
        try:
            output = crea_promemoria("domani alle 9", "Andare a fare la spesa da Lidl")
        finally:
            context.current_profile.reset(token)
        assert "Promemoria impostato" in output
        assert "Latte" in output and "Pane" in output
        rows = database._fb_get_reminders("mamma")
        assert len(rows) == 1
        assert rows[0]["include_todos"] is True
        assert rows[0]["status"] == "pending"

    def test_elenca_e_annulla(self):
        database._fb_add_reminder("io", "Chiamare il medico", "2026-11-17T08:00:00Z")
        token = context.current_profile.set("io")
        try:
            elenco = elenca_promemoria()
            assert "Chiamare il medico" in elenco
            esito = annulla_promemoria("1")
        finally:
            context.current_profile.reset(token)
        assert "annullato" in esito.lower()
        assert database._fb_get_reminders("io") == []

    def test_promemoria_non_spesa_non_allegare_la_lista(self):
        database._fb_add_todo("Latte", "io")
        token = context.current_profile.set("io")
        try:
            output = crea_promemoria("domani alle 9", "Chiamare il medico")
        finally:
            context.current_profile.reset(token)
        assert "Promemoria impostato" in output
        assert "Latte" not in output
        rows = database._fb_get_reminders("io")
        assert rows[0]["include_todos"] is False


class TestEndpointPromemoria:
    def test_lista_conferma_e_annulla(self, client, auth_headers):
        database._fallback_write("family_reminders", [])
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = database._fb_add_reminder("io", "Ritirare un pacco", future, True)

        lista = client.get("/promemoria", headers=auth_headers)
        assert lista.status_code == 200
        data = lista.json()["data"]
        assert any(item["id"] == row["id"] for item in data)

        ack = client.post(f"/promemoria/{row['id']}/programmato", headers=auth_headers)
        assert ack.status_code == 200 and ack.json()["status"] == "ok"
        assert database._fb_get_reminders("io")[0]["local_scheduled_at"]

        deleted = client.delete(f"/promemoria/{row['id']}", headers=auth_headers)
        assert deleted.status_code == 200 and deleted.json()["status"] == "ok"
        assert database._fb_get_reminders("io") == []

    def test_isolamento_tra_profili(self, client, auth_headers):
        database._fallback_write("family_reminders", [])
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        database._fb_add_reminder("mamma", "Segreto di mamma", future, False)
        lista = client.get("/promemoria", headers=auth_headers)
        assert lista.status_code == 200
        assert lista.json()["data"] == []


class TestSchedulerPromemoria:
    def setup_method(self):
        database._fallback_write("family_reminders", [])
        database._fallback_write("family_todos", [])

    def test_invia_push_se_non_locale(self, monkeypatch):
        from app import scheduler

        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = database._fb_add_reminder("io", "Promemoria push", past, True)
        chiamate = []

        def fake_invia(profile, titolo, messaggio, dati=None):
            chiamate.append((profile, titolo, messaggio, dati))
            return 1

        monkeypatch.setattr(scheduler, "invia_a_profilo", fake_invia)
        scheduler.job_promemoria_due()
        assert chiamate and chiamate[0][0] == "io"
        assert database._fb_get_reminders("io") == []

    def test_notifica_locale_non_duplica_la_push(self, monkeypatch):
        from app import scheduler

        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = database._fb_add_reminder("io", "Già locale", past, False)
        database._fb_mark_reminder_local_scheduled(row["id"], "io")
        chiamate = []
        monkeypatch.setattr(scheduler, "invia_a_profilo", lambda *args, **kwargs: chiamate.append(args) or 1)
        scheduler.job_promemoria_due()
        assert not chiamate
        assert database._fb_get_reminders("io") == []

    def test_senza_dispositivi_resta_pendente(self, monkeypatch):
        from app import scheduler

        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        database._fb_add_reminder("io", "Senza device", past, False)
        monkeypatch.setattr(scheduler, "invia_a_profilo", lambda *args, **kwargs: 0)
        scheduler.job_promemoria_due()
        assert len(database._fb_get_reminders("io")) == 1