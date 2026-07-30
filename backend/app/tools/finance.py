"""
Tools finanziari per ATLAS AI v3.0 (crypto, azioni, cambio, budget).

Il budget/spese viene salvato in Supabase (family_expenses) con fallback
trasparente su file locale tramite database.add_spesa/get_budget_summary,
non più direttamente tramite budget.json.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import requests

from app.core.database import add_spesa as _db_add_spesa
from app.core.database import get_budget_summary as _db_budget_summary
from app.core.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_TIMEOUT = 6


def _safe_requests_json(url: str, timeout: int = _DEFAULT_TIMEOUT):
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------- Crypto ----------------
def get_crypto_price(coin_id: str) -> str:
    """Ottiene prezzo e variazione 24h di una criptovaluta da CoinGecko."""
    if not coin_id or not coin_id.strip().isalnum():
        return "ID moneta non valido. Usa: bitcoin, ethereum, solana, cardano, dogecoin, polkadot, litecoin."
    try:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={quote(coin_id)}&vs_currencies=usd,eur&include_24hr_change=true"
        )
        data = _safe_requests_json(url)
        d = data.get(coin_id.lower())
        if not d:
            return (
                "Moneta non trovata in CoinGecko. Prova: bitcoin, ethereum, solana, "
                "cardano, dogecoin, polkadot, litecoin."
            )
        usd = float(d.get("usd", 0.0))
        eur = float(d.get("eur", 0.0))
        change = float(d.get("usd_24h_change", 0.0) or 0.0)
        arrow = "📈" if change >= 0 else "📉"
        return (
            f"{coin_id.upper()}: ${usd:,.2f} | €{eur:,.2f} | "
            f"24h: {arrow}{change:.1f}%"
        )
    except requests.RequestException as exc:
        log.warning("get_crypto_price rete: %s", exc)
        return "Servizio CoinGecko non raggiungibile al momento."
    except Exception as exc:
        log.exception("get_crypto_price errore: %s", exc)
        return "Impossibile recuperare il prezzo della criptovaluta."


def get_top_crypto(limit: int = 5) -> str:
    """Classifica top N criptovalute per capitalizzazione."""
    limit = max(1, min(int(limit or 5), 25))
    try:
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&order=market_cap_desc&per_page={limit}"
        )
        data = _safe_requests_json(url)
        if not isinstance(data, list) or not data:
            return "Dati classifica non disponibili al momento."
        rows: list[str] = []
        for i, c in enumerate(data, 1):
            name = c.get("name", "?")
            symbol = str(c.get("symbol", "?")).upper()
            price = float(c.get("current_price", 0.0) or 0.0)
            cap = float(c.get("market_cap", 0.0) or 0.0)
            rows.append(
                f"{i}. {name} ({symbol}): ${price:,.2f} | Cap: ${cap:,.0f}"
            )
        return "\n".join(rows)
    except requests.RequestException as exc:
        log.warning("get_top_crypto rete: %s", exc)
        return "Impossibile raggiungere CoinGecko al momento."
    except Exception as exc:
        log.exception("get_top_crypto: %s", exc)
        return "Errore nel recupero della classifica crypto."


# ---------------- Tassi di cambio ----------------
def get_exchange_rate(base: str, target: str) -> str:
    """Tasso di cambio ufficiale tra due valute (es. EUR -> ALL per Lek Albanese)."""
    if not (base and target) or len(base) != 3 or len(target) != 3:
        return "Codice valuta non valido. Usa formati ISO a 3 lettere (es. EUR, USD, ALL)."
    try:
        b, t = base.upper(), target.upper()
        url = f"https://api.exchangerate-api.com/v4/latest/{quote(b)}"
        data = _safe_requests_json(url, timeout=8)
        rates = data.get("rates") or {}
        rate = rates.get(t)
        if rate is None:
            return f"Valuta target {t} non disponibile tra quelle restituite dal servizio."
        return f"1 {b} = {float(rate):.4f} {t}"
    except requests.RequestException as exc:
        log.warning("get_exchange_rate rete: %s", exc)
        return "Servizio tassi di cambio non raggiungibile."
    except Exception as exc:
        log.exception("get_exchange_rate: %s", exc)
        return "Errore nel recupero del tasso di cambio."


# ---------------- Budget (persistente su Supabase) ----------------
def traccia_spesa(importo: float, categoria: str, descrizione: str = "") -> str:
    """Registra una spesa. Chiamabile anche da Gemini tramite function calling."""
    try:
        imp = float(importo)
        if imp <= 0:
            return "Importo non valido (deve essere positivo)."
    except (TypeError, ValueError):
        return "Importo non valido: inserisci un numero."

    cat = (categoria or "Altro").strip()[:50]
    desc = (descrizione or "").strip()[:500]
    slug_default = "io"
    try:
        esito = _db_add_spesa(importo=imp, categoria=cat, descrizione=desc, slug=slug_default)
    except Exception as exc:
        log.exception("traccia_spesa errore DB: %s", exc)
        return f"Registrazione fallita: {exc}"
    base = f"✅ Spesa di €{imp:.2f} registrata in '{cat}'."
    if desc:
        base += f" Nota: {desc}."
    if isinstance(esito, str) and esito:
        base += f" [{esito}]"
    return base


def riepilogo_budget() -> str:
    """Riepilogo spese per categoria e totale (dati da Supabase o fallback)."""
    try:
        summary = _db_budget_summary()
    except Exception as exc:
        log.exception("riepilogo_budget: %s", exc)
        return "Impossibile recuperare il riepilogo budget."

    totale = float(summary.get("totale", 0.0) or 0.0)
    dettaglio = summary.get("dettaglio") or []
    if totale <= 0 or not dettaglio:
        return "Nessuna spesa registrata. Usa 'Traccia spesa 20 cibo Latte e pane' per iniziare."
    righe = [f"💰 Totale speso: €{totale:.2f}", "📊 Per categoria:"]
    for row in dettaglio:
        c = row.get("categoria", "Altro")
        v = float(row.get("importo", 0.0) or 0.0)
        pct = float(row.get("percentuale", 0.0) or 0.0)
        righe.append(f"   {c}: €{v:.2f} ({pct:.0f}%)")
    return "\n".join(righe)


# ---------------- Azioni ----------------
def get_stock_price(ticker: str) -> str:
    """Prezzo di un'azione tramite Alpha Vantage (chiave opzionale NEWSAPI_KEY -> ALPHA_VANTAGE_KEY)."""
    if not ticker or not ticker.replace(".", "").isalnum():
        return "Ticker non valido (es. AAPL, MSFT, GOOGL)."
    key = os.getenv("ALPHA_VANTAGE_KEY", "demo")
    try:
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=GLOBAL_QUOTE&symbol={quote(ticker.upper())}&apikey={quote(key)}"
        )
        data = _safe_requests_json(url, timeout=8)
        q = data.get("Global Quote") or {}
        if not q:
            return "Azione non trovata o API demo limitata. Configura ALPHA_VANTAGE_KEY nel .env."
        price = float(q.get("05. price", 0.0) or 0.0)
        if price <= 0:
            return "Prezzo non disponibile per questo ticker."
        delta = q.get("10. change percent") or "N/A"
        return f"{ticker.upper()}: ${price:,.2f} | Δ: {delta}"
    except requests.RequestException as exc:
        log.warning("get_stock_price rete: %s", exc)
        return "Impossibile raggiungere Alpha Vantage al momento."
    except Exception as exc:
        log.exception("get_stock_price: %s", exc)
        return "Errore nel recupero del prezzo azionario."
