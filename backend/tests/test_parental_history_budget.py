"""Test di controllo genitore, cronologia chat sincronizzata e report budget."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.core import parental


def _profilo_bambino(client, auth_headers, nome="Bimbo Test"):
    risposta = client.post(
        "/profili",
        json={"nome": nome, "pin": "4321", "livello_italiano": "A2"},
        headers=auth_headers,
    )
    assert risposta.status_code == 200, risposta.text
    return risposta.json()["data"]["slug"]


def _token(client, slug, pin="4321"):
    login = client.post("/auth/pin", json={"profilo": slug, "pin": pin}).json()
    assert login["auth"] is True
    return {"Authorization": f"Bearer {login['token']}"}


def _finestra_chiusa() -> tuple[str, str]:
    """Fascia che non contiene l'ora attuale (gestisce anche la mezzanotte)."""
    adesso = datetime.now()
    inizio = f"{(adesso.hour + 1) % 24:02d}:{adesso.minute:02d}"
    fine = f"{adesso.hour:02d}:{adesso.minute:02d}"
    return inizio, fine


class TestControlloGenitore:
    def test_default_non_attivo(self):
        limiti = parental.limits_for({"tipo": "adulto"})
        assert limiti["attivo"] is False
        assert parental.check({"slug": "io", "tipo": "adulto"}) == (True, "")

    def test_fascia_oraria_anche_a_cavallo_di_mezzanotte(self):
        limiti = {"attivo": True, "ora_inizio": "21:00", "ora_fine": "07:00"}
        assert parental.is_within_hours(limiti, datetime(2026, 1, 1, 23, 30)) is True
        assert parental.is_within_hours(limiti, datetime(2026, 1, 1, 6, 30)) is True
        assert parental.is_within_hours(limiti, datetime(2026, 1, 1, 12, 0)) is False
        diurno = {"attivo": True, "ora_inizio": "08:00", "ora_fine": "20:00"}
        assert parental.is_within_hours(diurno, datetime(2026, 1, 1, 8, 0)) is True
        assert parental.is_within_hours(diurno, datetime(2026, 1, 1, 20, 0)) is False

    def test_admin_imposta_limiti_e_me_li_espone(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers)
        inizio, fine = _finestra_chiusa()

        salvataggio = client.post(
            f"/profili/{slug}/limiti",
            json={
                "attivo": True,
                "ora_inizio": inizio,
                "ora_fine": fine,
                "messaggi_giorno": 2,
                "contenuti_bambino": True,
            },
            headers=auth_headers,
        )
        assert salvataggio.status_code == 200
        assert salvataggio.json()["status"] == "ok"

        headers = _token(client, slug)
        me = client.get("/auth/me", headers=headers).json()
        assert me["tipo"] == "bambino"
        assert me["limiti"]["attivo"] is True
        assert me["limiti"]["messaggi_giorno"] == 2
        # Il PIN non esce mai dal backend.
        assert "pin_hash" not in me

    def test_fuori_orario_la_chat_e_bloccata(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers, nome="Bimbo Orario")
        inizio, fine = _finestra_chiusa()
        client.post(
            f"/profili/{slug}/limiti",
            json={"attivo": True, "ora_inizio": inizio, "ora_fine": fine, "messaggi_giorno": 0},
            headers=auth_headers,
        )
        headers = _token(client, slug)

        risposta = client.post("/chat", json={"msg": "Ciao"}, headers=headers)
        assert risposta.status_code == 403
        assert "chat è disponibile" in risposta.json()["message"]

    def test_limite_giornaliero(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers, nome="Bimbo Limite")
        client.post(
            f"/profili/{slug}/limiti",
            json={"attivo": True, "ora_inizio": "00:00", "ora_fine": "23:59", "messaggi_giorno": 1},
            headers=auth_headers,
        )
        headers = _token(client, slug)

        primo = client.post("/chat", json={"msg": "Ciao"}, headers=headers)
        assert primo.status_code == 200
        secondo = client.post("/chat", json={"msg": "Ancora"}, headers=headers)
        assert secondo.status_code == 403
        assert "messaggi di oggi" in secondo.json()["message"]

    def test_solo_admin_puo_impostare_i_limiti(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers, nome="Bimbo Ruolo")
        headers = _token(client, slug)
        negato = client.post(
            f"/profili/{slug}/limiti",
            json={"attivo": True},
            headers=headers,
        )
        assert negato.status_code == 403

    def test_tool_bloccati_per_bambino(self):
        bloccati = parental.blocked_tools_for({"tipo": "bambino", "limiti": {"attivo": True}})
        assert "traccia_spesa" in bloccati
        assert "web_search" in bloccati
        assert parental.blocked_tools_for({"tipo": "adulto"}) == set()


class TestCronologiaChat:
    def test_cronologia_condivisa_e_ricerca(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers, nome="Storico Test")
        headers = _token(client, slug)
        client.post("/chat", json={"msg": "ricetta della pasta"}, headers=headers)
        client.post("/chat", json={"msg": "orario del treno"}, headers=headers)

        cronologia = client.get("/chat/cronologia", headers=headers).json()["data"]
        testi = [row["testo"] for row in cronologia]
        assert "ricetta della pasta" in testi
        assert all(row["ruolo"] in ("user", "ai") for row in cronologia)

        ricerca = client.get("/chat/cronologia?q=treno", headers=headers).json()["data"]
        assert any("treno" in (row["testo"] or "") for row in ricerca)
        assert not any("ricetta" in (row["testo"] or "") for row in ricerca)

    def test_cronologia_solo_del_proprio_profilo(self, client, auth_headers):
        primo = _profilo_bambino(client, auth_headers, nome="Storico Uno")
        secondo = _profilo_bambino(client, auth_headers, nome="Storico Due")
        client.post("/chat", json={"msg": "segreto di uno"}, headers=_token(client, primo))

        altri = client.get("/chat/cronologia", headers=_token(client, secondo)).json()["data"]
        assert all("segreto di uno" not in (row["testo"] or "") for row in altri)


class TestReportBudget:
    def test_report_mensile_con_soglia_sforata(self, client, auth_headers):
        client.post(
            "/budget/spesa",
            json={"importo": 120.0, "categoria": "Cibo", "descrizione": "spesa"},
            headers=auth_headers,
        )
        salvataggio = client.post(
            "/budget/limiti",
            json={"limiti": {"Cibo": 100.0}},
            headers=auth_headers,
        )
        assert salvataggio.status_code == 200
        assert salvataggio.json()["data"]["Cibo"] == 100.0

        report = client.get("/budget/report", headers=auth_headers).json()["data"]
        cibo = next(row for row in report["dettaglio"] if row["categoria"] == "Cibo")
        assert cibo["limite"] == 100.0
        assert cibo["sforato"] is True
        assert cibo["percentuale_limite"] == 120.0
        assert report["avvisi"]

    def test_limiti_solo_admin(self, client, auth_headers):
        slug = _profilo_bambino(client, auth_headers, nome="Budget Ruolo")
        negato = client.post(
            "/budget/limiti",
            json={"limiti": {"Cibo": 10.0}},
            headers=_token(client, slug),
        )
        assert negato.status_code == 403

    def test_limiti_non_validi_vengono_ignorati(self, client, auth_headers):
        risposta = client.post(
            "/budget/limiti",
            json={"limiti": {"Cibo": 0, "Altro": -5}},
            headers=auth_headers,
        )
        assert risposta.status_code == 200
        assert risposta.json()["data"] == {}
