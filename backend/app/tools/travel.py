"""
Tools viaggio e meteo per ATLAS AI v3.0.

- Meteo e geocoding: Open-Meteo (gratuito, nessuna chiave)
- Voli: Amadeus Self-Service (free tier, richiede chiave gratuita) oppure
  link reale di ricerca su Google Flights/Skyscanner se la chiave non c'è.
"""
from __future__ import annotations

import math
import os
import re
import urllib.parse
from datetime import date, datetime

import requests

from app.core.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_TIMEOUT = 8


def _geo_code(city: str, count: int = 1, language: str = "it") -> list[dict] | None:
    """Geocoding città tramite Open-Meteo (API gratuita)."""
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": max(count, 1), "language": language},
            timeout=_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results")
        return list(results) if results else None
    except requests.RequestException as exc:
        log.warning("geo_code fallita per %s: %s", city, exc)
        return None
    except (ValueError, TypeError) as exc:  # pragma: no cover
        log.exception("geo_code errore: %s", exc)
        return None


# ---------------- Meteo ----------------
def get_weather(city: str) -> str:
    """Meteo attuale e probabilità di pioggia per una città (Open-Meteo).

    Args:
        city: Nome della città, es. "Milano".
    """
    if not city or not city.strip():
        return "Quale città? Es: 'Meteo Milano'"
    geo = _geo_code(city.strip())
    if not geo:
        return f"Città '{city}' non trovata. Prova con il nome corretto."
    first = geo[0]
    nome = first.get("name") or city.strip()
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": first["latitude"],
                "longitude": first["longitude"],
                "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 1,
            },
            timeout=_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        out = (
            f"🌤️ {nome}: {current.get('temperature_2m', '?')}°C | "
            f"Vento: {current.get('wind_speed_10m', '?')} km/h"
        )
        precip = daily.get("precipitation_probability_max")
        if isinstance(precip, list) and precip:
            out += f"\n🌧️ Pioggia oggi: {precip[0]}%"
        tmax = daily.get("temperature_2m_max")
        tmin = daily.get("temperature_2m_min")
        if isinstance(tmax, list) and isinstance(tmin, list) and tmax and tmin:
            out += f"\n🌡️ Min {tmin[0]}°C · Max {tmax[0]}°C"
        return out
    except requests.RequestException as exc:
        log.warning("get_weather fallita: %s", exc)
        return "Servizio meteo non raggiungibile al momento."
    except (ValueError, KeyError, TypeError) as exc:
        log.exception("get_weather errore: %s", exc)
        return "Errore nel recupero del meteo."


def get_weather_forecast(city: str, days: int = 3) -> str:
    """Previsioni meteo per i prossimi N giorni (max 16).

    Args:
        city: Nome della città.
        days: Numero di giorni (1-16, default 3).
    """
    if not city or not city.strip():
        return "Scrivi una città. Es: 'Previsioni Roma 5 giorni'"
    giorni = max(1, min(int(days or 3), 16))
    geo = _geo_code(city.strip())
    if not geo:
        return f"Città '{city}' non trovata."
    nome = geo[0].get("name") or city.strip()
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": geo[0]["latitude"],
                "longitude": geo[0]["longitude"],
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,wind_speed_10m_max"
                ),
                "timezone": "auto",
                "forecast_days": giorni,
            },
            timeout=_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        daily = response.json().get("daily") or {}
        giorni_iso = daily.get("time") or []
        if not giorni_iso:
            return "Nessuna previsione disponibile per questa località."
        tmax = daily.get("temperature_2m_max") or []
        tmin = daily.get("temperature_2m_min") or []
        precip = daily.get("precipitation_probability_max") or []
        righe = [f"📅 Previsioni {nome} ({giorni} giorni):"]
        for index, giorno in enumerate(giorni_iso[:giorni]):
            righe.append(
                f"  {giorno}: max {tmax[index] if index < len(tmax) else '?'}°C "
                f"min {tmin[index] if index < len(tmin) else '?'}°C  "
                f"🌧️{precip[index] if index < len(precip) else '?'}%"
            )
        return "\n".join(righe)
    except requests.RequestException as exc:
        log.warning("get_weather_forecast fallita: %s", exc)
        return "Servizio previsioni meteo offline al momento."
    except (ValueError, KeyError, TypeError) as exc:
        log.exception("get_weather_forecast: %s", exc)
        return "Errore nel recupero delle previsioni."


# ---------------- Distanza ----------------
def calcola_distanza(punto_a: str, punto_b: str) -> str:
    """Distanza in linea d'aria e tempo stimato in auto tra due città.

    Args:
        punto_a: Città di partenza.
        punto_b: Città di arrivo.
    """
    if not (punto_a and punto_b):
        return "Scrivi due città. Es: 'Distanza Milano Roma'"
    geo_a = _geo_code(punto_a.strip())
    geo_b = _geo_code(punto_b.strip())
    if not geo_a:
        return f"Località '{punto_a}' non trovata."
    if not geo_b:
        return f"Località '{punto_b}' non trovata."
    try:
        a, b = geo_a[0], geo_b[0]
        lat1, lon1 = math.radians(float(a["latitude"])), math.radians(float(a["longitude"]))
        lat2, lon2 = math.radians(float(b["latitude"])), math.radians(float(b["longitude"]))
        dlon, dlat = lon2 - lon1, lat2 - lat1
        calc = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        km = 6371 * 2 * math.atan2(math.sqrt(calc), math.sqrt(max(0.0, 1 - calc)))
        ore = km / 80.0
        return (
            f"📍 Da {a.get('name', punto_a)} a {b.get('name', punto_b)}: "
            f"{km:.0f} km (~{ore:.1f} ore in auto)"
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.exception("calcola_distanza errore: %s", exc)
        return "Impossibile calcolare la distanza al momento."


# ---------------- Voli ----------------
def _amadeus_base() -> str:
    env = os.getenv("AMADEUS_ENV", "test").strip().lower()
    return "https://api.amadeus.com" if env == "production" else "https://test.api.amadeus.com"


def _amadeus_token() -> str | None:
    client_id = os.getenv("AMADEUS_CLIENT_ID", "").strip()
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    try:
        response = requests.post(
            f"{_amadeus_base()}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        response.raise_for_status()
        return str(response.json().get("access_token") or "") or None
    except (requests.RequestException, ValueError) as exc:
        log.warning("Amadeus auth fallita: %s", exc)
        return None


def _amadeus_city_code(keyword: str, token: str) -> str | None:
    try:
        response = requests.get(
            f"{_amadeus_base()}/v1/reference-data/locations",
            params={"keyword": keyword, "subType": "CITY,AIRPORT", "page[limit]": 1},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()
        data = (response.json().get("data") or [])
        if data:
            return str(data[0].get("iataCode") or "") or None
    except (requests.RequestException, ValueError) as exc:
        log.warning("Amadeus geocoding '%s' fallito: %s", keyword, exc)
    return None


def cerca_volo(destinazione: str, data: str, origine: str = "Milano") -> str:
    """Cerca voli reali per una destinazione e una data.

    Args:
        destinazione: Città di arrivo (es. "Londra").
        data: Data di partenza in formato YYYY-MM-DD.
        origine: Città di partenza (default "Milano").
    """
    if not (destinazione and data):
        return "Dimmi destinazione e data. Es: 'Volo Londra 2025-08-15'"
    dest = destinazione.strip()[:60]
    orig = (origine or "Milano").strip()[:60]
    data_clean = data.strip()[:10]

    try:
        datetime.strptime(data_clean, "%Y-%m-%d")
    except ValueError:
        return "Data non valida: usa il formato YYYY-MM-DD (es. 2025-08-15)."

    token = _amadeus_token()
    if token:
        origen_code = _amadeus_city_code(orig, token)
        dest_code = _amadeus_city_code(dest, token)
        if origen_code and dest_code:
            try:
                response = requests.get(
                    f"{_amadeus_base()}/v2/shopping/flight-offers",
                    params={
                        "originLocationCode": origen_code,
                        "destinationLocationCode": dest_code,
                        "departureDate": data_clean,
                        "adults": 1,
                        "currencyCode": "EUR",
                        "max": 5,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=20,
                )
                response.raise_for_status()
                offers = (response.json().get("data") or [])
                if offers:
                    righe = [f"✈️ Voli {orig} ({origen_code}) → {dest} ({dest_code}) · {data_clean}:"]
                    for index, offer in enumerate(offers[:5], 1):
                        price = (offer.get("price") or {}).get("grandTotal", "?")
                        itineraries = offer.get("itineraries") or []
                        durata = itineraries[0].get("duration", "?") if itineraries else "?"
                        righe.append(
                            f"  {index}. €{price} · durata {durata} · "
                            f"posti {(offer.get('numberOfBookableSeats') or '?')}"
                        )
                    return "\n".join(righe)
                return f"Nessun volo disponibile trovato per {orig} → {dest} il {data_clean}."
            except (requests.RequestException, ValueError, KeyError) as exc:
                log.warning("Amadeus ricerca voli fallita: %s", exc)

    # Fallback reale (nessuna simulazione): link di ricerca precompilato.
    google_url = (
        "https://www.google.com/travel/flights?q="
        + urllib.parse.quote(f"Flights from {orig} to {dest} on {data_clean}")
    )
    skyscanner_url = (
        "https://www.skyscanner.it/trasporti/voli/?q="
        + urllib.parse.quote(f"{orig} {dest} {data_clean}")
    )
    return (
        f"✈️ Ricerca voli {orig} → {dest} il {data_clean}:\n"
        "Per prezzi in tempo reale serve la chiave gratuita Amadeus "
        "(AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET, piano Self-Service senza costi).\n"
        f"Nel frattempo puoi cercare qui:\n  • Google Flights: {google_url}\n"
        f"  • Skyscanner: {skyscanner_url}"
    )


def oggi_iso() -> str:
    """Data odierna ISO (helper per i tool)."""
    return date.today().isoformat()


_ = re  # mantenuto per compatibilità import
