"""
Test del client MCP reale (JSON-RPC 2.0 / Streamable HTTP).

Avvia un mini server MCP in un thread locale e verifica handshake, elenco tool
e chiamata tool: nessuna rete esterna, nessuna simulazione nel codice testato.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.tools import mcp_bridge


class _MCPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - nome richiesto da BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send({"jsonrpc": "2.0", "id": None, "error": {"message": "JSON non valido"}})
            return

        _MCPHandler.received.append(body)
        method = body.get("method")
        request_id = body.get("id")

        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if method == "initialize":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "test-mcp", "version": "1.0.0"},
                    },
                },
                {"Mcp-Session-Id": "sessione-test"},
            )
            return

        if method == "tools/list":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Ripete il testo ricevuto",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"testo": {"type": "string"}},
                                },
                            }
                        ]
                    },
                }
            )
            return

        if method == "tools/call":
            params = body.get("params") or {}
            arguments = params.get("arguments") or {}
            if params.get("name") != "echo":
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "Tool sconosciuto"},
                    }
                )
                return
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Eco: {arguments.get('testo', '')}"}]
                    },
                }
            )
            return

        self._send(
            {"jsonrpc": "2.0", "id": request_id, "error": {"message": f"Metodo {method} sconosciuto"}}
        )

    def _send(self, payload: dict, extra_headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args) -> None:  # silenzia il log del server di test
        return


@pytest.fixture
def mcp_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
    monkeypatch.setenv("MCP_SERVERS", json.dumps({"test": {"url": url}}))
    mcp_bridge._MCP_SESSIONS.clear()
    _MCPHandler.received.clear()
    yield url
    server.shutdown()
    server.server_close()
    mcp_bridge._MCP_SESSIONS.clear()


class TestMCPClient:
    def test_elenca_server_configurati(self, mcp_server):
        output = mcp_bridge.mcp_elenca_server()
        assert "test" in output
        assert mcp_server in output

    def test_elenca_tool_del_server(self, mcp_server):
        output = mcp_bridge.mcp_elenca_tool("test")
        assert "echo" in output
        assert "testo" in output

    def test_chiama_tool_reale(self, mcp_server):
        output = mcp_bridge.mcp_chiama_tool("test", "echo", json.dumps({"testo": "ciao famiglia"}))
        assert output == "Eco: ciao famiglia"

    def test_handshake_inviato_una_sola_volta(self, mcp_server):
        mcp_bridge.mcp_elenca_tool("test")
        mcp_bridge.mcp_elenca_tool("test")
        initialize_calls = [msg for msg in _MCPHandler.received if msg.get("method") == "initialize"]
        assert len(initialize_calls) == 1

    def test_server_sconosciuto(self, mcp_server):
        output = mcp_bridge.mcp_elenca_tool("inesistente")
        assert "non configurato" in output

    def test_argomenti_json_non_valido(self, mcp_server):
        output = mcp_bridge.mcp_chiama_tool("test", "echo", "{non-json")
        assert "JSON" in output

    def test_tool_sconosciuto_restituisce_errore(self, mcp_server):
        output = mcp_bridge.mcp_chiama_tool("test", "sconosciuto", "{}")
        assert "⚠️" in output

    def test_senza_configurazione(self, monkeypatch):
        monkeypatch.delenv("MCP_SERVERS", raising=False)
        output = mcp_bridge.mcp_elenca_server()
        assert "Nessun server MCP configurato" in output
