"""
Tools viaggio e meteo per ATLAS AI v3.0.
"""
from __future__ import annotations

import math
import urllib.parse

import requests

from app.core.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_TIMEOUT = 6


def _geo_code(city: str, count: int = 1, language: str = "it") -> list[dict] | None:
    """Geocoding città tramite Open-Meteo (API gratuita)."""
    try:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={urllib.parse.quote(city)}&count={max(count,1)}&language={language}"
        )
        resp = requests.get(url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results")
        if not results:
            return None
        return list(results)
    except requests.RequestException as exc:
        log.warning("geo_code fallita per %s: %s", city, exc)
        return None
    except Exception as exc:  # pragma: no cover
        log.exception("geo_code errore: %s", exc)
        return None


# ---------------- Meteo ----------------
def get_weather(city: str) -> str:
    """Meteo attuale e previsione giorno per una città (Open-Meteo)."""
    if not city or not city.strip():
        return "Quale città? Es: 'Meteo Milano'"
    geo = _geo_code(city.strip(), count=1)
    if not geo:
        return f"Città '{city}' non trovata. Prova con il nome corretto."
    first = geo[0]
    lat, lon = float(first["latitude"]), float(first["longitude"])
    nome = first.get("name") or city.strip()
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current_weather=true&daily=temperature_max,temperature_min,precipitation_probability_max"
            "&timezone=auto"
        )
        resp = requests.get(url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
        m = resp.json()
        cw = m.get("current_weather") or {}
        daily = m.get("daily") or {}
        temp = cw.get("temperature", "?")
        wind = cw.get("windspeed", "?")
        out = f"🌤️ {nome}: {temp}°C | Vento: {wind} km/h"
        precip = daily.get("precipitation_probability_max")
        if isinstance(precip, list) and precip:
            out += f"\n🌧️ Pioggia oggi: {precip[0]}%"
        return out
    except requests.RequestException as exc:
        log.warning("get_weather fallita: %s", exc)
        return "Servizio meteo non raggiungibile al momento."
    except Exception as exc:
        log.exception("get_weather errore: %s", exc)
        return "Errore nel recupero del meteo."


def get_weather_forecast(city: str, days: int = 3) -> str:
    """Previsioni meteo per i prossimi N giorni (max 16, default 3)."""
    if not city or not city.strip():
        return "Scrivi una città. Es: 'Previsioni Roma 5 giorni'"
    days = max(1, min(int(days or 3), 16))
    geo = _geo_code(city.strip(), count=1)
    if not geo:
        return f"Città '{city}' non trovata."
    lat, lon = float(geo[0]["latitude"]), float(geo[0]["longitude"])
    nome = geo[0].get("name") or city.strip()
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&daily=temperature_max,temperature_min,precipitation_probability_max,wind_speed_10m_max"
            f"&timezone=auto&forecast_days={days}"
        )
        resp = requests.get(url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
        m = resp.json()
        daily = m.get("daily") or {}
        tm = daily.get("time") or []
        tmax = daily.get("temperature_max") or []
        tmin = daily.get("temperature_min") or []
        precip = daily.get("precipitation_probability_max") or []
        if not tm:
            return "Nessuna previsione disponibile per questa località."
        righe = [f"📅 Previsioni {nome} ({days} giorni):"]
        for i in range(min(days, len(tm))):
            righe.append(
                f"  {tm[i]}: max {tmax[i]}°C min {tmin[i]}°C  "
                f"🌧️{precip[i] if i < len(precip) else '?'}%"
            )
        return "\n".join(righe)
    except requests.RequestException as exc:
        log.warning("get_weather_forecast fallita: %s", exc)
        return "Servizio previsioni meteo offline al momento."
    except Exception as exc:
        log.exception("get_weather_forecast: %s", exc)
        return "Errore nel recupero delle previsioni."


# ---------------- Distanza ----------------
def calcola_distanza(punto_a: str, punto_b: str) -> str:
    """Distanza (linea d'aria e tempo stimato in auto) tra due città."""
    if not (punto_a and punto_b):
        return "Scrivi due città. Es: 'Distanza Milano Roma'"
    geo_a = _geo_code(punto_a.strip(), count=1, language="it")
    geo_b = _geo_code(punto_b.strip(), count=1, language="it")
    if not geo_a:
        return f"Località '{punto_a}' non trovata."
    if not geo_b:
        return f"Località '{punto_b}' non trovata."
    try:
        a, b = geo_a[0], geo_b[0]
        lat1, lon1 = math.radians(float(a["latitude"])), math.radians(float(a["longitude"]))
        lat2, lon2 = math.radians(float(b["latitude"])), math.radians(float(b["longitude"]))
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        calc = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        km = 6371 * 2 * math.atan2(math.sqrt(calc), math.sqrt(1 - calc))
        ore = km / 80.0  # velocità media autostrada
        return (
            f"📍 Da {a.get('name', punto_a)} a {b.get('name', punto_b)}: "
            f"{km:.0f} km (~{ore:.1f} ore in auto)"
        )
    except Exception as exc:
        log.exception("calcola_distanza errore: %s", exc)
        return "Impossibile calcolare la distanza al momento."


# ---------------- Voli ----------------
def cerca_volo(destinazione: str, data: str, origine: str = "Milano") -> str:
    """Cerca voli (simulato: Amadeus richiede chiave pagata)."""
    if not (destinazione and data):
        return "Dimmi destinazione e data. Es: 'Volo Londra 2025-08-15'"
    dest = destinazione.strip()[:60]
    data_clean = data.strip()[:20]
    orig = (origine or "Milano").strip()[:60]
    return (
        f"✈️ Ricerca voli da {orig} a {dest} per il {data_clean}.\n"
        "[Nota: i voli reali richiedono la chiave Amadeus API nel .env. "
        "Nel frattempo puoi confrontare prezzi su Skyscanner o Kayak.]"
    )
