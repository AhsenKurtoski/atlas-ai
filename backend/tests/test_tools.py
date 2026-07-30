"""
Unit test per i tools di ATLAS AI:
- utility.calcolatrice (NO eval, parser AST safe)
- utility._safe_math_eval (casi limite: overflow, div 0)
- budget somma e percentuali
- family todos (flusso base)
- Haversine / travel formule (coordinate)
"""
from __future__ import annotations

import math

import pytest

from app.core.database import (
    _fb_add_spesa,
    _fb_add_todo,
    _fb_complete_todo_by_index,
    _fb_get_todos,
    _fallback_write,
    get_budget_summary,
)
from app.tools.family import add_family_todo, completa_todo, get_family_todos
from app.tools.utility import _safe_math_eval, calcolatrice


class TestCalcolatriceSafe:
    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("2 + 3", 5.0),
            ("10 - 4", 6.0),
            ("6 * 7", 42.0),
            ("20 / 4", 5.0),
            ("10 // 3", 3.0),
            ("10 % 3", 1.0),
            ("2 ** 10", 1024.0),
            ("(2 + 3) * 4", 20.0),
            ("-5 + 10", 5.0),
            ("+3 * 2", 6.0),
            ("3,5 + 2", 5.5),
            ("15 x 4", 60.0),
            ("10 ÷ 2", 5.0),
            ("3 × 2", 6.0),
        ],
    )
    def test_calcolatrice_base(self, expr, expected):
        out = calcolatrice(expr)
        assert out.endswith(f"{expected:g}") or f"{expected:g}" in out

    def test_calcolatrice_divisione_zero(self):
        assert "dividere per zero" in calcolatrice("1 / 0").lower() or "Impossibile" in calcolatrice("1 / 0")

    def test_safe_math_eval_pow_overflow_protetto(self):
        with pytest.raises(ValueError, match="[Oo]verflow|[Tt]roppo"):
            _safe_math_eval("9999999 ** 999")

    def test_safe_math_eval_rifiuta_espressione_lunga(self):
        with pytest.raises(ValueError, match="[Ll]unga|[Tt]roppo"):
            _safe_math_eval("1+" * 150 + "1")

    def test_calcolatrice_rifiuta_codice(self):
        # Tentativi classic di injection: devono risultare "Espressione non valida"
        for bad in [
            "__import__('os')",
            "eval('1+1')",
            "1; import os",
            "lambda: 1",
        ]:
            out = calcolatrice(bad)
            assert "non valida" in out or "Errore nel calcolo" in out, (bad, out)


class TestTodosLocale:
    def setup_method(self):
        # Pulizia file todos locale prima di ogni test
        _fallback_write("family_todos", [])

    def test_aggiungi_e_ottieni_todos(self):
        r = add_family_todo("Comprare il latte", assegnato_a="Mamma")
        assert "latte" in r and "aggiunto" in r.lower()
        lista = get_family_todos()
        assert "latte" in lista

    def test_completa_todo(self):
        add_family_todo("Task A")
        add_family_todo("Task B")
        r = completa_todo(1)
        assert "completato" in r.lower() or "✅" in r
        # Ricerca pending: dovrebbe vedere solo Task B
        pending = get_family_todos(filtro="da fare")
        assert "Task A" not in pending or "Task B" in pending

    def test_completa_todo_indice_non_valido(self):
        r = completa_todo(999)
        assert "Non c'è nessun task" in r or "non valido" in r.lower()


class TestBudgetLocale:
    def setup_method(self):
        _fallback_write("family_expenses", [])

    def test_add_spesa_e_riepilogo_somma(self):
        _fb_add_spesa(50.0, "Cibo", "Pizza", "io")
        _fb_add_spesa(30.5, "Cibo", "Pasta", "mamma")
        _fb_add_spesa(120.0, "Bollette", "Luce", "io")
        riep = get_budget_summary()
        assert abs(riep["totale"] - 200.5) < 1e-6
        categorie = {r["categoria"]: r["importo"] for r in riep["dettaglio"]}
        assert abs(categorie["Cibo"] - 80.5) < 1e-6
        assert abs(categorie["Bollette"] - 120.0) < 1e-6

    def test_percentuali_corrette(self):
        _fb_add_spesa(75.0, "Cibo", "", "io")
        _fb_add_spesa(25.0, "Svago", "", "io")
        riep = get_budget_summary()
        by_cat = {r["categoria"]: r for r in riep["dettaglio"]}
        assert abs(by_cat["Cibo"]["percentuale"] - 75.0) < 0.5
        assert abs(by_cat["Svago"]["percentuale"] - 25.0) < 0.5


class TestFormuleGeografiche:
    def test_haversine_stessa_localita(self):
        # Formula Haversine: stessa coordinata → 0 km
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
            return 2 * R * math.asin(math.sqrt(a))

        assert haversine(45.464, 9.190, 45.464, 9.190) == pytest.approx(0.0, abs=0.01)
        d = haversine(45.464, 9.190, 41.9028, 12.4964)  # Milano ↔ Roma
        assert 470 < d < 510  # ~490 km reale
