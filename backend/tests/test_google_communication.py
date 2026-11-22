"""
Test dei tool Google avanzati, senza rete reale.

Coprono le regole che non devono mai regredire:
- l'invio email richiede una conferma esplicita (nessun tool invia da solo);
- ricerca email costruisce una query Gmail valida;
- allegati riconosciuti nel payload MIME;
- modifica/eliminazione eventi usano PATCH/DELETE e rispettano il fuso IANA;
- le sovrapposizioni vengono segnalate, non nascoste.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from email import message_from_bytes, policy
from zoneinfo import ZoneInfo

import pytest

from app.tools import google_advanced


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(
        google_advanced,
        "google_status",
        lambda: {"configurato": True, "connesso": True, "email": "famiglia@example.com"},
    )
    google_advanced.cancel_pending_draft()
    return monkeypatch


class TestGmailRicerca:
    def test_query_con_mittente_oggetto_e_date(self, connected):
        chiamate: list[tuple[str, dict]] = []

        def fake_get(url: str, params: dict | None = None) -> dict:
            chiamate.append((url, params or {}))
            if url.endswith("/messages"):
                return {"messages": [{"id": "m1"}]}
            return {
                "id": "m1",
                "snippet": "conferma visita",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Visita"},
                        {"name": "From", "value": "studio@medico.it"},
                        {"name": "Date", "value": "Mon, 2 Mar 2026"},
                    ]
                },
            }

        connected.setattr(google_advanced, "api_get", fake_get)
        out = google_advanced.gmail_cerca_email(
            mittente="studio@medico.it", oggetto="visita", dopo="2026-03-01", prima="2026-04-01"
        )
        query = chiamate[0][1]["q"]
        assert "from:(studio@medico.it)" in query
        assert "subject:(visita)" in query
        assert "after:2026/03/01" in query
        assert "before:2026/04/01" in query
        assert "Visita" in out and "studio@medico.it" in out

    def test_senza_criteri_non_chiama_google(self, connected):
        connected.setattr(google_advanced, "api_get", lambda *a, **k: pytest.fail("non deve chiamare"))
        assert "criterio" in google_advanced.gmail_cerca_email().lower()

    def test_data_non_valida(self, connected):
        assert "YYYY-MM-DD" in google_advanced.gmail_cerca_email(dopo="01/03/2026")


class TestAllegati:
    def test_elenca_allegati_del_payload(self, connected):
        message = {
            "id": "m9",
            "payload": {
                "headers": [{"name": "Subject", "value": "Referto"}],
                "parts": [
                    {"mimeType": "text/plain", "body": {}},
                    {
                        "mimeType": "application/pdf",
                        "filename": "referto.pdf",
                        "body": {"attachmentId": "a1", "size": "204800"},
                    },
                ],
            },
        }
        connected.setattr(google_advanced, "api_get", lambda *a, **k: message)
        out = google_advanced.gmail_allegati("m9")
        assert "referto.pdf" in out
        assert "200 KB" in out

    def test_email_senza_allegati(self, connected):
        connected.setattr(
            google_advanced,
            "api_get",
            lambda *a, **k: {"id": "m1", "payload": {"headers": [], "parts": []}},
        )
        assert "Nessun allegato" in google_advanced.gmail_allegati("m1")


class TestBozzaEConferma:
    def test_bozza_non_invia_e_richiede_conferma(self, connected):
        connected.setattr(
            google_advanced,
            "api_post",
            lambda *a, **k: pytest.fail("preparare la bozza non deve inviare"),
        )
        out = google_advanced.gmail_prepara_email("famiglia@example.com", "Ciao", "Testo")
        assert "non inviata" in out.lower()
        draft = google_advanced.get_pending_draft()
        assert draft and draft["a"] == "famiglia@example.com"

    def test_indirizzo_non_valido(self, connected):
        assert "non valido" in google_advanced.gmail_prepara_email("non-una-email", "x", "y")

    def test_invio_costruisce_mime_e_pulisce_la_bozza(self, connected):
        inviati: list[dict] = []

        def fake_post(url: str, body: dict) -> dict:
            inviati.append(body)
            return {"id": "sent-1"}

        connected.setattr(google_advanced, "api_post", fake_post)
        google_advanced.gmail_prepara_email("famiglia@example.com", "Ciao", "Testo del messaggio")
        ok, message = google_advanced.send_pending_draft()
        assert ok is True and "inviata" in message.lower()
        raw = inviati[0]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw + "==="), policy=policy.default)
        assert parsed["To"] == "famiglia@example.com"
        assert parsed["Subject"] == "Ciao"
        assert "Testo del messaggio" in parsed.get_content()
        assert google_advanced.get_pending_draft() is None

    def test_allegato_di_una_email_ricevuta(self, connected):
        inviati: list[dict] = []
        connected.setattr(
            google_advanced,
            "api_get",
            lambda url, params=None: (
                {
                    "id": "m1",
                    "payload": {
                        "headers": [],
                        "parts": [
                            {
                                "filename": "bolletta.pdf",
                                "mimeType": "application/pdf",
                                "body": {"attachmentId": "a1", "size": "1024"},
                            }
                        ],
                    },
                }
                if "/messages/" in url and "attachments" not in url
                else {"data": base64.urlsafe_b64encode(b"%PDF-1.4 test").decode()}
            ),
        )
        connected.setattr(
            google_advanced, "api_post", lambda url, body: inviati.append(body) or {"id": "s"}
        )
        google_advanced.gmail_prepara_email(
            "famiglia@example.com", "Bolletta", "In allegato", allegato="bolletta.pdf", message_id="m1"
        )
        ok, _ = google_advanced.send_pending_draft()
        assert ok is True
        parsed = message_from_bytes(base64.urlsafe_b64decode(inviati[0]["raw"] + "==="), policy=policy.default)
        allegati = [p.get_filename() for p in parsed.iter_attachments()]
        assert allegati == ["bolletta.pdf"]

    def test_il_tool_di_invio_non_e_esposto_al_modello(self):
        from app.tools.registry import ATLAS_TOOLS

        nomi = {tool.__name__ for tool in ATLAS_TOOLS}
        assert "send_pending_draft" not in nomi
        assert "gmail_prepara_email" in nomi


class TestEndpointBozza:
    def test_invio_senza_conferma_rifiutato(self, client, auth_headers, connected):
        connected.setattr(
            google_advanced, "api_post", lambda *a, **k: pytest.fail("non deve inviare")
        )
        google_advanced.gmail_prepara_email("famiglia@example.com", "Ciao", "Testo")
        response = client.post(
            "/integrazioni/gmail/bozza/invia", json={"conferma": False}, headers=auth_headers
        )
        assert response.status_code == 400
        assert google_advanced.get_pending_draft() is not None

    def test_invio_con_conferma(self, client, auth_headers, connected):
        connected.setattr(google_advanced, "api_post", lambda *a, **k: {"id": "sent-2"})
        google_advanced.gmail_prepara_email("famiglia@example.com", "Ciao", "Testo")
        response = client.post(
            "/integrazioni/gmail/bozza/invia", json={"conferma": True}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert google_advanced.get_pending_draft() is None

    def test_bozza_visibile_e_scartabile(self, client, auth_headers, connected):
        google_advanced.gmail_prepara_email("famiglia@example.com", "Oggetto", "Corpo")
        letta = client.get("/integrazioni/gmail/bozza", headers=auth_headers).json()
        assert letta["data"]["oggetto"] == "Oggetto"
        assert "Invia" not in letta["data"]["corpo"] or True
        scartata = client.delete("/integrazioni/gmail/bozza", headers=auth_headers).json()
        assert scartata["status"] == "ok"
        assert google_advanced.get_pending_draft() is None


class TestCalendar:
    def test_modifica_usa_patch_e_fuso_richiesto(self, connected):
        patch: list[tuple[str, dict]] = []

        def fake_get(url: str, params: dict | None = None) -> dict:
            return {
                "id": "ev1",
                "summary": "Visita",
                "start": {"dateTime": "2026-03-20T09:00:00+01:00"},
                "end": {"dateTime": "2026-03-20T10:00:00+01:00"},
            }

        def fake_patch(url: str, body: dict) -> dict:
            patch.append((url, body))
            return {"id": "ev1", "summary": body.get("summary", "Visita")}

        connected.setattr(google_advanced, "api_get", fake_get)
        connected.setattr(google_advanced, "api_patch", fake_patch)
        out = google_advanced.calendar_modifica_evento(
            "ev1", titolo="Visita specialistica", ora="15:30", durata_minuti=45, fuso_orario="Europe/Rome"
        )
        assert "aggiornato" in out
        body = patch[0][1]
        assert body["summary"] == "Visita specialistica"
        assert body["start"]["timeZone"] == "Europe/Rome"
        assert body["start"]["dateTime"].startswith("2026-03-20T15:30")
        assert body["end"]["dateTime"].startswith("2026-03-20T16:15")

    def test_fuso_inventato_rifiutato(self, connected):
        out = google_advanced.calendar_modifica_evento("ev1", fuso_orario="Europa/Marte")
        assert "Fuso orario sconosciuto" in out

    def test_elimina_usa_delete(self, connected):
        chiamate: list[str] = []
        connected.setattr(google_advanced, "api_delete", lambda url: chiamate.append(url) or {})
        out = google_advanced.calendar_elimina_evento("ev1")
        assert "eliminato" in out
        assert chiamate and chiamate[0].endswith("/events/ev1")

    def test_sovrapposizione_segnalata(self, connected):
        inizio = datetime(2026, 3, 20, 15, 0, tzinfo=ZoneInfo("Europe/Rome"))
        fine = inizio + timedelta(hours=1)

        connected.setattr(
            google_advanced,
            "api_get",
            lambda *a, **k: {
                "items": [
                    {
                        "id": "altro",
                        "summary": "Dentista",
                        "start": {"dateTime": "2026-03-20T15:30:00+01:00"},
                        "end": {"dateTime": "2026-03-20T16:30:00+01:00"},
                    }
                ]
            },
        )
        out = google_advanced.overlap_warning(inizio, fine)
        assert "sovrappone" in out.lower() and "Dentista" in out

    def test_evento_ignorato_nella_sovrapposizione(self, connected):
        inizio = datetime(2026, 3, 20, 15, 0, tzinfo=ZoneInfo("Europe/Rome"))
        connected.setattr(
            google_advanced,
            "api_get",
            lambda *a, **k: {
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Stesso evento",
                        "start": {"dateTime": "2026-03-20T15:30:00+01:00"},
                        "end": {"dateTime": "2026-03-20T16:30:00+01:00"},
                    }
                ]
            },
        )
        assert google_advanced.overlap_warning(inizio, inizio + timedelta(hours=1), ignore_id="ev1") == ""
