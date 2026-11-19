"""
Report mensile del budget: totale, confronto col mese precedente, soglie per
categoria e avvisi di sforamento.

Le soglie si salvano nelle impostazioni (`soglie.budget_categoria`), così il
report è disponibile anche alla chat (`riepilogo_budget` resta invariato).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.core import database


def _month_key(value: Optional[str]) -> str:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
        except ValueError:
            pass
    return date.today().strftime("%Y-%m")


def _previous_month(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    if month_number == 1:
        return f"{year - 1}-12"
    return f"{year}-{month_number - 1:02d}"


def _category_totals(rows: list[dict], month: str) -> tuple[float, dict[str, float]]:
    totals: dict[str, float] = {}
    for row in rows:
        created = str(row.get("created_at") or "")
        if created[:7] != month:
            continue
        category = str(row.get("category") or "Altro")
        totals[category] = totals.get(category, 0.0) + float(row.get("amount") or 0)
    return round(sum(totals.values()), 2), {key: round(value, 2) for key, value in totals.items()}


def limits() -> dict[str, float]:
    """Soglie mensili per categoria configurate dall'utente."""
    settings = database.get_settings() or {}
    raw = (settings.get("soglie") or {}).get("budget_categoria") or {}
    result: dict[str, float] = {}
    if isinstance(raw, dict):
        for category, value in raw.items():
            try:
                amount = float(value)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                result[str(category)] = round(amount, 2)
    return result


def save_limits(raw: dict[str, Any]) -> dict[str, float]:
    """Valida e salva le soglie, ignorando valori non numerici o <= 0."""
    clean: dict[str, float] = {}
    for category, value in (raw or {}).items():
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            clean[str(category).strip()[:50]] = round(amount, 2)
    database.update_settings({"soglie": {"budget_categoria": clean}})
    return clean


def monthly_report(month: Optional[str] = None) -> dict[str, Any]:
    month = _month_key(month)
    previous = _previous_month(month)
    rows = database.get_expense_rows()

    totale, per_categoria = _category_totals(rows, month)
    totale_precedente, categorie_precedenti = _category_totals(rows, previous)
    soglie = limits()

    dettaglio = []
    avvisi = []
    for category, importo in sorted(per_categoria.items(), key=lambda item: item[1], reverse=True):
        limite = soglie.get(category)
        percentuale = round((importo / limite) * 100, 1) if limite else None
        sforato = bool(limite and importo > limite)
        dettaglio.append(
            {
                "categoria": category,
                "importo": importo,
                "limite": limite,
                "percentuale_limite": percentuale,
                "sforato": sforato,
                "mese_precedente": categorie_precedenti.get(category, 0.0),
            }
        )
        if sforato:
            avvisi.append(
                f"{category}: €{importo:.2f} su un limite di €{limite:.2f} "
                f"(+€{importo - limite:.2f})."
            )

    return {
        "mese": month,
        "totale": totale,
        "dettaglio": dettaglio,
        "soglie": soglie,
        "avvisi": avvisi,
        "mese_precedente": {"mese": previous, "totale": totale_precedente},
        "variazione_percentuale": (
            round(((totale - totale_precedente) / totale_precedente) * 100, 1)
            if totale_precedente
            else None
        ),
    }
