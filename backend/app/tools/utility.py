"""
Utility tools per ATLAS AI v3.0.

Sostituito eval() con un parser matematico safe basato su ast.literal_eval
e un set limitato di operatori consentiti. Nessuna valutazione di codice
arbitrario.
"""
from __future__ import annotations

import ast
import ipaddress
import operator
import os
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import requests

from app.core.logging_config import get_logger

log = get_logger(__name__)

# ---------------- Imports opzionali (graceful degradation) ----------------
try:
    import wikipedia  # type: ignore[import-not-found]

    wikipedia.set_lang("it")
    WIKIPEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - ambiente senza dipendenza
    WIKIPEDIA_AVAILABLE = False
    wikipedia = None  # type: ignore[assignment]

try:
    from duckduckgo_search import DDGS  # type: ignore[import-not-found]

    DDGS_AVAILABLE = True
except ImportError:  # pragma: no cover
    DDGS_AVAILABLE = False
    DDGS = None  # type: ignore[assignment,misc]

_OP_MAP: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_MAX_EXPRESSION_LEN = 200


def _safe_eval_node(node: ast.AST) -> Any:
    """Valuta in modo ricorsivo un AST di sola espressione matematica."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    # ast.Num e ast.Str sono stati rimossi in Python 3.14;
    # manteniamo la compatibilità con le versioni più vecchie usando getattr safe.
    _ast_Num = getattr(ast, "Num", None)
    if _ast_Num is not None and isinstance(node, _ast_Num):  # pragma: no cover
        return node.n
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OP_MAP:
            raise ValueError(f"Operatore non consentito: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Divisione per zero non consentita")
        if op_type is ast.Pow:
            if abs(left) > 10**6 or right > 100:
                raise ValueError("Esponenziale troppo grande (overflow protection)")
        return _OP_MAP[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OP_MAP:
            raise ValueError(f"Operatore unario non consentito: {op_type.__name__}")
        operand = _safe_eval_node(node.operand)
        return _OP_MAP[op_type](operand)  # type: ignore[call-arg]
    raise ValueError("Tipo di nodo AST non consentito")


def _safe_math_eval(expr: str) -> float:
    """Parser matematico safe senza eval. Supporta: +, -, *, /, //, %, **, ()."""
    if len(expr) > _MAX_EXPRESSION_LEN:
        raise ValueError(f"Espressione troppo lunga (> {_MAX_EXPRESSION_LEN} caratteri)")
    tree = ast.parse(expr, mode="eval")
    result = _safe_eval_node(tree)
    if isinstance(result, (int, float)):
        return float(result)
    raise ValueError("Risultato non numerico")


def web_search(query: str, max_results: int = 4) -> str:
    """Cerca informazioni sul web in tempo reale con DuckDuckGo."""
    try:
        results: list[str] = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results), 1):
                title = r.get("title", "(no titolo)")
                body = (r.get("body") or "")[:200]
                results.append(f"{i}. **{title}**\n   {body}")
        return "\n\n".join(results) if results else "Nessun risultato trovato."
    except requests.RequestException as exc:
        log.warning("web_search fallita (rete): %s", exc)
        return "Errore di rete durante la ricerca. Riprova più tardi."
    except Exception as exc:
        log.exception("web_search errore generico: %s", exc)
        return "Errore durante la ricerca web."


def cerca_wikipedia(query: str, lingua: str = "it") -> str:
    """Cerca su Wikipedia nella lingua specificata."""
    try:
        wikipedia.set_lang(lingua)
        page = wikipedia.summary(query, sentences=3)
        return str(page) if page else "Nessun risultato su Wikipedia."
    except wikipedia.exceptions.PageError:
        return f"Nessuna voce Wikipedia trovata per '{query}'."
    except wikipedia.exceptions.DisambiguationError as exc:
        options = ", ".join(str(o) for o in list(getattr(exc, "options", []))[:6])
        return f"Voce ambigua. Possibili alternative: {options}"
    except requests.RequestException as exc:
        log.warning("cerca_wikipedia rete: %s", exc)
        return "Impossibile raggiungere Wikipedia al momento."
    except Exception as exc:
        log.exception("cerca_wikipedia: %s", exc)
        return "Errore nella ricerca Wikipedia."


def get_news(argomento: str = "tecnologia", page_size: int = 5) -> str:
    """Ultime notizie tramite NewsAPI.org. Usa chiave opzionale NEWSAPI_KEY."""
    api_key = os.getenv("NEWSAPI_KEY", "demo")
    try:
        url = (
            f"https://newsapi.org/v2/everything?q={quote(argomento)}"
            f"&language=it&pageSize={page_size}&apiKey={api_key}"
        )
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            return "Notizie non disponibili (API key mancante o non valida)."
        articles = data.get("articles") or []
        if not articles:
            return f"Nessuna notizia recente su '{argomento}'."
        return "\n\n".join(
            f"📰 {a.get('title', 'Senza titolo')}\n   {(a.get('description') or '')[:150]}"
            for a in articles[:page_size]
        )
    except requests.RequestException as exc:
        log.warning("get_news fallita: %s", exc)
        return "Impossibile recuperare le notizie al momento (errore di rete)."
    except Exception as exc:
        log.exception("get_news errore: %s", exc)
        return "Errore recupero notizie."


def get_time_timezone(timezone: str = "Europe/Rome") -> str:
    """Ora esatta in qualsiasi fuso orario IANA."""
    try:
        r = requests.get(f"http://worldtimeapi.org/api/timezone/{quote(timezone)}", timeout=5)
        r.raise_for_status()
        data = r.json()
        dt = data.get("datetime", "")
        if len(dt) < 19:
            raise ValueError("Formato data non valido")
        return (
            f"🕐 {timezone.replace('_', ' ')}: {dt[11:19]} "
            f"({dt[8:10]}/{dt[5:7]}/{dt[:4]})"
        )
    except requests.RequestException as exc:
        log.warning("get_time_timezone rete: %s", exc)
        now = datetime.now().isoformat()
        return (
            f"🕐 {timezone.replace('_', ' ')} (locale): {now[11:19]} "
            f"({now[8:10]}/{now[5:7]}/{now[:4]})"
        )
    except Exception as exc:
        log.exception("get_time_timezone: %s", exc)
        return "Fuso orario non valido o servizio offline."


def get_ip_info(ip: str = "") -> str:
    """Informazioni geolocalizzazione IP. Stringa vuota = IP pubblico chiamante."""
    try:
        if ip:
            ipaddress.ip_address(ip)  # validazione, raise ValueError se non valido
        url = f"http://ip-api.com/json/{quote(ip)}" if ip else "http://ip-api.com/json/"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            return "Impossibile recuperare informazioni IP."
        return (
            f"🌐 IP: {data.get('query')} | {data.get('city', '?')}, "
            f"{data.get('country', '?')} | ISP: {data.get('isp', '?')}"
        )
    except ValueError:
        return "Indirizzo IP non valido."
    except requests.RequestException as exc:
        log.warning("get_ip_info rete: %s", exc)
        return "Errore di rete durante la richiesta IP."
    except Exception as exc:
        log.exception("get_ip_info: %s", exc)
        return "Errore informazioni IP."


def genera_qr_code(testo: str) -> str:
    """Genera URL di un QR code (200x200) tramite servizio pubblico."""
    if not testo:
        return "Fornisci del testo per generare il QR code."
    return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(testo)}"


def calcolatrice(espressione: str) -> str:
    """Calcola un'espressione matematica usando parser AST safe (NO eval)."""
    try:
        if not espressione:
            return "Fornisci un'espressione da calcolare (es. 15 * 3 + 20 / 4)."
        cleaned = espressione.replace("x", "*").replace("×", "*").replace("÷", "/").replace(",", ".")
        cleaned = cleaned.replace(" ", "")
        if not cleaned:
            return "Espressione vuota."
        result = _safe_math_eval(cleaned)
        formatted = f"{result:g}" if result.is_integer() else f"{result:.4f}".rstrip("0").rstrip(".")
        return f"{espressione} = {formatted}"
    except ZeroDivisionError:
        return "Impossibile dividere per zero."
    except (SyntaxError, ValueError) as exc:
        return f"Espressione non valida: {exc}. Usa formato: 15 * 3 + 20 / 4"
    except Exception as exc:
        log.exception("calcolatrice errore inatteso: %s", exc)
        return "Errore nel calcolo. Riprova con un'espressione più semplice."
