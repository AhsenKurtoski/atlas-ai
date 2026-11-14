"""
Test meteo (Open-Meteo): nomi delle variabili e parsing della risposta.

Regressione: l'API ha rinominato `temperature_max/min` in
`temperature_2m_max/min`; con i vecchi nomi rispondeva HTTP 400 e il meteo
sembrava "non raggiungibile".
"""
from __future__ import annotations

from app.tools import travel


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def _fake_get(calls: list[tuple[str, dict]]):
    def fake(url: str, params: dict | None = None, timeout: int | None = None):
        calls.append((url, params or {}))
        if "geocoding" in url:
            return _FakeResponse(
                {"results": [{"name": "Milano", "latitude": 45.46, "longitude": 9.19}]}
            )
        return _FakeResponse(
            {
                "current": {
                    "temperature_2m": 18.5,
                    "wind_speed_10m": 7.2,
                    "weather_code": 1,
                },
                "daily": {
                    "time": ["2026-11-14", "2026-11-15"],
                    "temperature_2m_max": [22, 19],
                    "temperature_2m_min": [12, 10],
                    "precipitation_probability_max": [30, 70],
                    "wind_speed_10m_max": [10, 14],
                },
            }
        )

    return fake


class TestMeteo:
    def test_get_weather_usa_le_variabili_corrette(self, monkeypatch):
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(travel.requests, "get", _fake_get(calls))

        out = travel.get_weather("Milano")

        assert "18.5" in out
        assert "30%" in out
        assert "Min 12" in out and "Max 22" in out

        forecast_call = next(params for url, params in calls if "forecast" in url)
        daily = forecast_call["daily"]
        assert "temperature_2m_max" in daily
        assert "temperature_2m_min" in daily
        assert "temperature_max" not in daily

    def test_get_weather_forecast_parsing(self, monkeypatch):
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(travel.requests, "get", _fake_get(calls))

        out = travel.get_weather_forecast("Milano", days=2)

        assert "2026-11-14" in out and "2026-11-15" in out
        assert "max 22" in out and "min 12" in out
        assert "70%" in out

    def test_citta_non_valida(self):
        assert "Quale città" in travel.get_weather("")
