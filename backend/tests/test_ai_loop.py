"""Test del loop di function calling Gemini con un client completamente finto.

Non serve una chiave API: il client simula due turni di tool e la risposta
finale. Verifica che ATLAS esegua *tutti* i tool richiesti, invii i risultati
corretti a Gemini e rispetti il limite di turni configurato.
"""
from __future__ import annotations

import pytest

from app.ai_router import GeminiRouter


class FakeCall:
    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class FakeResponse:
    def __init__(self, text: str | None = None, calls: list[FakeCall] | None = None) -> None:
        self.text = text
        self.function_calls = calls or []


class FakeChat:
    def __init__(self) -> None:
        self.responses: list[FakeResponse] = []
        self.sent: list[object] = []

    def send_message(self, message):
        self.sent.append(message)
        if not self.responses:
            raise AssertionError("Il router ha inviato più messaggi del previsto")
        return self.responses.pop(0)


class FakeChats:
    def __init__(self, chat: FakeChat) -> None:
        self._chat = chat
        self.config = None

    def create(self, **kwargs):
        self.config = kwargs
        return self._chat


class FakeClient:
    def __init__(self, chat: FakeChat) -> None:
        self.chats = FakeChats(chat)


@pytest.fixture
def router(monkeypatch):
    router = GeminiRouter()
    router.chiavi = ["chiave-finta-per-test"]
    chat = FakeChat()
    client = FakeClient(chat)
    monkeypatch.setattr(router, "_get_client", lambda: client)
    return router, chat


def test_loop_esegue_tutti_i_tool_e_restituisce_la_risposta(router, monkeypatch):
    router_obj, chat = router
    chat.responses = [
        FakeResponse(
            calls=[
                FakeCall("browser_apri", {"url": "https://example.com"}),
                FakeCall("browser_vedi", {}),
            ]
        ),
        FakeResponse(text="Ho aperto la pagina e letto il contenuto."),
    ]
    dispatched: list[tuple[str, dict]] = []

    def fake_dispatch(name: str, args: dict) -> str:
        dispatched.append((name, args))
        return f"RISULTATO:{name}"

    monkeypatch.setattr(router_obj, "_dispatch_tool", fake_dispatch)
    esito = router_obj.chiedi("Apri example.com e dimmi cosa c'è", {"nome": "Ada"})

    assert esito == "Ho aperto la pagina e letto il contenuto."
    assert dispatched == [
        ("browser_apri", {"url": "https://example.com"}),
        ("browser_vedi", {}),
    ]
    assert len(chat.sent) == 2
    parts = chat.sent[1]
    assert isinstance(parts, list) and len(parts) == 2
    assert [part.function_response.name for part in parts] == [
        "browser_apri",
        "browser_vedi",
    ]
    assert chat.sent[0] == "Apri example.com e dimmi cosa c'è"


def test_loop_rispetta_il_limite_di_turni(router, monkeypatch):
    router_obj, chat = router
    monkeypatch.setenv("AGENT_MAX_TOOL_TURNS", "2")
    chat.responses = [
        FakeResponse(calls=[FakeCall("browser_vedi", {})]) for _ in range(3)
    ]
    dispatched: list[str] = []

    def fake_dispatch(name: str, args: dict) -> str:
        dispatched.append(name)
        return "risultato"

    monkeypatch.setattr(router_obj, "_dispatch_tool", fake_dispatch)
    esito = router_obj.chiedi("Continua all'infinito", {"nome": "Ada"})

    assert len(chat.sent) == 3  # richiesta iniziale + 2 turni di tool
    assert dispatched == ["browser_vedi", "browser_vedi"]
    assert "non posso rispondere" in esito.lower()
