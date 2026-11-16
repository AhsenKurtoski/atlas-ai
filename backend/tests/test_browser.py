"""Test end-to-end dell'agente browser (Chromium headless reale).

I test avviano un piccolo server HTTP locale con JavaScript, form e una
seconda pagina: verificano navigazione, lettura, click, compilazione, select,
scroll, cronologia, chiusura e blocco SSRF. Non usano mock del browser.
"""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.browser import (
    _request_allowed,
    browser_service,
    clear_dns_cache,
    shutdown_browser,
)
from app.tools.browser import (
    browser_apri,
    browser_chiudi,
    browser_clicca,
    browser_indietro,
    browser_premi,
    browser_scorri,
    browser_seleziona,
    browser_spunta,
    browser_scrivi,
    browser_vedi,
)
from app.tools.registry import ATLAS_TOOLS, ATLAS_TOOLS_BY_NAME

PAGINA = """<!doctype html>
<html lang="it">
<head><meta charset="utf-8"><title>ATLAS Test</title></head>
<body>
  <h1>Ciao mondo</h1>
  <p>Pagina di prova per l'agente browser.</p>
  <a href="/next">Vai alla seconda</a>
  <form onsubmit="event.preventDefault(); document.getElementById('esito').textContent='Ciao '+document.getElementById('nome').value;">
    <label for="nome">Il tuo nome</label>
    <input id="nome" name="nome" placeholder="Scrivi il nome">
    <label for="lingua">Lingua</label>
    <select id="lingua" name="lingua">
      <option value="it">Italiano</option>
      <option value="en">Inglese</option>
    </select>
    <button id="saluta" type="submit">Saluta</button>
  </form>
  <div id="esito"></div>
  <button id="carica" onclick="setTimeout(function(){document.getElementById('esito').textContent='Caricato dopo';}, 200)">Carica</button>
  <label for="promo">Voglio le offerte</label>
  <input id="promo" name="promo" type="checkbox">
  <div style="height:1800px">Spazio per lo scroll</div>
</body>
</html>
"""

SECONDA = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Seconda pagina</title></head>
<body><h1>Seconda pagina</h1><p>Navigazione riuscita.</p><a href="/">Torna indietro</a></body>
</html>
"""

# Pagina servita da loopback con ALLOW_PRIVATE_FETCH=true, poi usata per
# verificare che XHR, immagini e iframe verso un host che risolve a 127.0.0.1
# vengano bloccati dal route guard DNS anche dopo il caricamento iniziale.
PAGINA_SSRF = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Test SSRF subrisorse</title></head>
<body>
  <h1>Test SSRF</h1>
  <button id="trigger" onclick="
    fetch('http://evil.example:{port}/xhr', {mode:'no-cors'})
      .then(function(){set('xhr-ok')}).catch(function(){set('xhr-blocked')});
    var img = new Image();
    img.src = 'http://evil.example:{port}/img';
    img.onerror = function(){set('img-error')};
    img.onload = function(){set('img-ok')};
    var frame = document.createElement('iframe');
    frame.src = 'http://evil.example:{port}/iframe';
    document.body.appendChild(frame);
  ">Trigger</button>
  <div id="log"></div>
  <script>function set(t){document.getElementById('log').textContent += t + ' ';}</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - API http.server
        self.server.requests.append(self.path)
        if self.path.startswith("/ssrf"):
            body = PAGINA_SSRF.replace("{port}", str(self.server.server_address[1]))
        elif self.path.startswith("/next"):
            body = SECONDA
        else:
            body = PAGINA
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):  # silenzia il log del server di test
        return


@pytest.fixture(scope="module")
def site_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def site_url(site_server):
    return f"http://127.0.0.1:{site_server.server_address[1]}/"


@pytest.fixture(autouse=True)
def _browser_env(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "true")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    monkeypatch.setenv("BROWSER_ENABLED", "true")
    clear_dns_cache()
    yield
    browser_chiudi()
    clear_dns_cache()


@pytest.fixture(scope="module", autouse=True)
def _stop_browser():
    yield
    shutdown_browser()


class TestRegistry:
    def test_tool_browser_registrati(self):
        nomi = {tool.__name__ for tool in ATLAS_TOOLS}
        attesi = {
            "browser_apri",
            "browser_vedi",
            "browser_clicca",
            "browser_scrivi",
            "browser_seleziona",
            "browser_premi",
            "browser_spunta",
            "browser_scorri",
            "browser_indietro",
            "browser_chiudi",
        }
        assert attesi <= nomi
        assert len(ATLAS_TOOLS) >= 45
        assert "Chromium" in (ATLAS_TOOLS_BY_NAME["browser_apri"].__doc__ or "")


class TestBrowserReale:
    def test_apri_e_vedi(self, site_url):
        output = browser_apri(site_url)
        assert "ATLAS Test" in output
        assert "Ciao mondo" in output
        assert "Vai alla seconda" in output
        assert "CAMPI COMPILABILI" in output

    def test_compila_e_clicca(self, site_url):
        browser_apri(site_url)
        compilato = browser_scrivi("Il tuo nome", "Ada")
        assert "Compilato" in compilato
        esito = browser_clicca("Saluta")
        assert "Cliccato" in esito
        assert "Ciao Ada" in esito

    def test_select_e_scroll(self, site_url):
        browser_apri(site_url)
        output = browser_seleziona("lingua", "Inglese")
        assert "Selezionato" in output
        scroll = browser_scorri("giu")
        assert "Scorrimento" in scroll

    def test_spunta_e_premi(self, site_url):
        browser_apri(site_url)
        checked = browser_spunta("Voglio le offerte")
        assert "selezionato" in checked.lower()
        pressed = browser_premi("Esc")
        assert "Premuto" in pressed

    def test_javascript_aggiorna_pagina(self, site_url):
        browser_apri(site_url)
        browser_clicca("#carica")
        assert "Caricato dopo" in browser_vedi()

    def test_navigazione_e_indietro(self, site_url):
        browser_apri(site_url)
        seconda = browser_clicca("Vai alla seconda")
        assert "Seconda pagina" in seconda
        assert "Navigazione riuscita" in browser_vedi()
        indietro = browser_indietro()
        assert "Ciao mondo" in indietro

    def test_chiudi_sessione(self, site_url):
        browser_apri(site_url)
        assert "chiuso" in browser_chiudi().lower()
        assert "Nessuna pagina aperta" in browser_vedi()

    def test_elemento_inesistente_errore_esplicito(self, site_url):
        browser_apri(site_url)
        output = browser_clicca("#non-esiste")
        assert "Elemento non trovato" in output

    def test_blocca_ssrf(self, site_url, monkeypatch):
        monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
        output = browser_apri(site_url)
        assert "URL non consentito" in output

    def test_blocca_dns_xhr_iframe_e_immagini(self, site_url, site_server, monkeypatch):
        browser_apri(site_url + "ssrf")
        site_server.requests.clear()
        monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "false")
        clear_dns_cache()

        def fake_getaddrinfo(host, port, *args, **kwargs):
            # Simula un dominio che risolve su loopback (DNS rebinding).
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

        monkeypatch.setattr("app.services.browser.socket.getaddrinfo", fake_getaddrinfo)
        browser_clicca("#trigger")
        assert "xhr-blocked" in browser_vedi()
        assert not [
            path for path in site_server.requests if path.startswith(("/xhr", "/img", "/iframe"))
        ]

    def test_sessioni_isolate_per_profilo(self, site_url):
        browser_service.open_page("alpha", site_url)
        browser_service.open_page("beta", site_url + "next")
        try:
            assert "ATLAS Test" in browser_service.view("alpha")
            assert "Seconda pagina" in browser_service.view("beta")
            browser_service.close("beta")
            assert "ATLAS Test" in browser_service.view("alpha")
        finally:
            browser_service.close("alpha")
            browser_service.close("beta")

    def test_browser_disattivato(self, site_url, monkeypatch):
        monkeypatch.setenv("BROWSER_ENABLED", "false")
        output = browser_apri(site_url)
        assert "Browser disattivato" in output


class TestIntegrazioneAgente:
    def test_chat_imposta_profilo_browser(self, client, auth_headers, monkeypatch):
        from app.ai_router import ai_router
        from app.services.browser import browser_profile

        visto: dict[str, str] = {}

        def fake_chiedi(prompt, profilo_utente, memoria=None, immagine=None):
            visto["slug"] = browser_profile.get()
            return "risposta di prova"

        monkeypatch.setattr(ai_router, "chiedi", fake_chiedi)
        response = client.post("/chat", json={"msg": "ciao"}, headers=auth_headers)
        assert response.status_code == 200
        assert visto["slug"] == "io"


class TestSicurezzaBrowser:
    def test_host_privati_bloccati(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
        assert not _request_allowed("http://127.0.0.1:8000/")
        assert not _request_allowed("http://localhost:3000/")
        assert not _request_allowed("http://192.168.1.10/")
        assert not _request_allowed("http://[::1]/") 
        assert not _request_allowed("file:///etc/passwd")

    def test_host_pubblici_e_schemi_sicuri(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
        assert _request_allowed("https://example.com/", check_dns=False)
        assert _request_allowed("data:image/png;base64,AAAA")

    def test_dns_privato_bloccato_anche_per_sottorisorse(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
        clear_dns_cache()
        chiamate = []

        def fake_getaddrinfo(host, port, *args, **kwargs):
            chiamate.append(host)
            ip = "10.0.0.7" if host.startswith("interno") else "93.184.216.34"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

        monkeypatch.setattr("app.services.browser.socket.getaddrinfo", fake_getaddrinfo)
        assert not _request_allowed("http://interno.example/immagine.png")
        assert not _request_allowed("http://interno.example/api")
        assert _request_allowed("https://pubblico.example/frame")
        assert chiamate.count("interno.example") == 1  # cache DNS

    def test_dns_fail_closed(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
        clear_dns_cache()

        def fake_getaddrinfo(*args, **kwargs):
            raise socket.gaierror("nome non risolvibile")

        monkeypatch.setattr("app.services.browser.socket.getaddrinfo", fake_getaddrinfo)
        assert not _request_allowed("https://non-risolvibile.example/")

    def test_opt_in_privato(self, monkeypatch):
        monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "true")
        assert _request_allowed("http://127.0.0.1:8000/")
