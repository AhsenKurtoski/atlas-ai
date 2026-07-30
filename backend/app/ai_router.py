"""
Router AI principale per ATLAS v3.0 basato sul SDK Google GenAI.

Caratteristiche:
- Rotazione automatica di 3 chiavi API Gemini in caso di errore "quota" / 429
- Function calling integrato con tutti i tool definiti in registry
- Sistema prompt personalizzato per lingua madre e livello italiano del profilo
- Supporto RAG (memoria conversazionale) opzionale tramite parametro `memoria`
- Eccezioni specifiche + logging strutturato

Questo modulo sostituisce le funzionalità duplicate in app.services.gemini_service
(oggi mantenuto come "legacy" per retrocompatibilità, ma non viene più importato
dal main).
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from google import genai

from app.core.logging_config import get_logger
from app.tools.registry import ATLAS_TOOLS

log = get_logger(__name__)

_MODEL = "gemini-2.0-flash"
_EMOJI_MODERATI = {"🔥", "✅", "📌", "⚠️", "💡", "✨", "🙂", "📊", "🌤️", "💰"}


class GeminiRouter:
    """Router principale per le interazioni con Google Gemini."""

    def __init__(self) -> None:
        raw_keys = [os.getenv(f"GEMINI_KEY_{i}", "") for i in range(1, 4)]
        cleaned = [k.strip() for k in raw_keys if k and k.strip() and not k.startswith("INSERISCI")]
        self.chiavi: list[str] = cleaned
        self.indice_corrente = 0
        log.info("Router Gemini inizializzato con %d chiave/i.", len(self.chiavi))

    # ---------- Gestione chiavi ----------
    def _get_client(self) -> genai.Client | None:
        if not self.chiavi:
            return None
        key = self.chiavi[self.indice_corrente % len(self.chiavi)]
        try:
            return genai.Client(api_key=key)
        except Exception as exc:  # pragma: no cover - init errori SDK
            log.error("Impossibile inizializzare client Gemini: %s", exc)
            return None

    def _rotate(self) -> None:
        if len(self.chiavi) <= 1:
            return
        old = self.indice_corrente
        self.indice_corrente = (self.indice_corrente + 1) % len(self.chiavi)
        log.warning("Rotazione chiave Gemini %d -> %d", old, self.indice_corrente)

    # ---------- Prompt ----------
    @staticmethod
    def _build_system_prompt(profilo: dict[str, Any], memoria: Iterable[dict] | None) -> str:
        nome = profilo.get("nome") or "Utente"
        madre = profilo.get("lingua_madre") or "Italiano"
        livello = profilo.get("livello_italiano") or "C1"
        memoria_hint = ""
        if memoria:
            righe = []
            for m in list(memoria)[-6:]:
                role = m.get("role", "user")
                text = str(m.get("content") or "")[:120]
                righe.append(f"- {'Utente' if role == 'user' else 'ATLAS'}: {text}")
            memoria_hint = (
                "\n\nULTIMI MESSAGGI (per contesto, non ripetere esplicitamente):\n"
                + "\n".join(righe)
            )
        return (
            f"Sei ATLAS AI v3.0, l'assistente personale e fidato di una famiglia italiana.\n"
            f"Stai parlando con: **{nome}**\n"
            f"Lingua madre di {nome}: {madre}\n"
            f"Livello di italiano attuale: {livello}\n"
            f"Adatta la complessità delle frasi al livello d'italiano. Se il livello è A2 o B1,\n"
            f"usa frasi corte, parole comuni e spiega i termini difficili. Se è madrelingua o C1+\n"
            f"puoi essere più ricco di dettagli.\n\n"
            f"REGOLE VITALI:\n"
            f"1. Usa SEMPRE i tool disponibili per rispondere (crypto, meteo, ricerca web,\n"
            f"   lista spesa, traduzioni, notizie, budget, voli, email, calendario).\n"
            f"2. Se NON hai un tool specifico, usa web_search prima di rispondere 'non lo so'.\n"
            f"3. Rispondi SEMPRE in ITALIANO corretto ma semplice.\n"
            f"4. Se noti errori di grammatica nel messaggio dell'utente, correggili GENTILMENTE\n"
            f"   solo alla fine della risposta. Non interrompere il flusso della conversazione.\n"
            f"5. Lista spesa: usa add_family_todo e get_family_todos.\n"
            f"6. Budget: usa traccia_spesa e riepilogo_budget.\n"
            f"7. Criptovalute: get_crypto_price o get_top_crypto.\n"
            f"8. Meteo: get_weather o get_weather_forecast.\n"
            f"9. Sii caloroso, familiare e conciso. Non usare emoji in eccesso.\n"
            f"10. Se l'utente chiede di fare qualcosa che non sai spiegagli chiaramente\n"
            f"    come abilitare la funzionalità (es. OAuth Gmail).\n"
            f"{memoria_hint}"
        )

    # ---------- Invocazione tool ----------
    def _dispatch_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        func = next((t for t in ATLAS_TOOLS if getattr(t, "__name__", None) == tool_name), None)
        if func is None:
            log.warning("Tool richiesto da Gemini non trovato: %s", tool_name)
            return f"[Tool '{tool_name}' non disponibile.]"
        try:
            result = func(**args)
            text = str(result) if result is not None else ""
            log.info("TOOL %s eseguito -> %d caratteri", tool_name, len(text))
            return text[:4000]
        except TypeError as exc:
            log.warning("Argomenti non validi per %s: %s", tool_name, exc)
            return f"[Argomenti non validi per tool '{tool_name}': {exc}]"
        except Exception as exc:  # pragma: no cover - tool errori di rete
            log.exception("Tool %s fallito: %s", tool_name, exc)
            return f"[Tool '{tool_name}' ha restituito un errore.]"

    # ---------- Entrypoint ----------
    def chiedi(
        self,
        prompt: str,
        profilo_utente: dict[str, Any],
        memoria: Iterable[dict] | None = None,
    ) -> str:
        """Invia un messaggio a Gemini con function calling e memoria opzionale."""
        if not prompt or not prompt.strip():
            return "Scrivimi qualcosa, sono qui per aiutarti! 😊"

        if not self.chiavi:
            return (
                "⚠️ Nessuna chiave Gemini valida nel file .env. "
                "Aggiungi GEMINI_KEY_1 e riavvia il backend per attivarmi."
            )

        system_prompt = self._build_system_prompt(profilo_utente, memoria or [])

        ultimo_errore: str | None = None
        for tentativo in range(max(1, len(self.chiavi))):
            client = self._get_client()
            if client is None:
                return "Client AI non disponibile. Controlla le chiavi Gemini nel file .env."
            try:
                chat = client.chats.create(
                    model=_MODEL,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=ATLAS_TOOLS,
                        temperature=0.6,
                    ),
                )
                risposta = chat.send_message(prompt.strip())

                # Gestione iterativa dei tool (fino a 4 turni per evitare loop)
                loop_safety = 0
                current = risposta
                while loop_safety < 5 and current and getattr(current, "function_calls", None):
                    loop_safety += 1
                    fc_list = list(current.function_calls) or []
                    if not fc_list:
                        break
                    responses: list[Any] = []
                    for fc in fc_list:
                        tool_name = str(fc.name)
                        args_raw = getattr(fc, "args", {}) or {}
                        args = {k: v for k, v in args_raw.items()}
                        log.info("[TOOL] %s(%s)", tool_name, str(args)[:120])
                        tool_result = self._dispatch_tool(tool_name, args)
                        responses.append(
                            genai.types.Part.from_function_response(
                                name=tool_name,
                                response={"result": tool_result},
                            )
                        )
                    if not responses:
                        break
                    current = chat.send_message(responses)

                testo = getattr(current, "text", None)
                if testo:
                    return str(testo).strip()
                ultimo_errore = "Risposta vuota da Gemini."
                # Try fallback: risposta precedente
                backup = getattr(risposta, "text", None)
                if backup:
                    return str(backup).strip()

            except Exception as exc:  # pragma: no cover
                err = str(exc).lower()
                log.warning("Gemini errore (tentativo %d): %s", tentativo + 1, exc)
                ultimo_errore = str(exc)
                if "quota" in err or "429" in err or "resourceexhausted" in err:
                    self._rotate()
                    continue
                # Non è un errore di quota: riportiamo all'utente in modo soft
                return (
                    "🙈 Scusa, ho avuto un problema temporaneo mentre pensavo alla risposta. "
                    "Puoi ripetere la domanda?\n\n"
                    f"Dettaglio tecnico: {str(exc)[:200]}"
                )

        # Siamo usciti dal ciclo: tutte le chiavi hanno avuto problemi
        return (
            "❌ Purtroppo al momento non posso rispondere. "
            "Tutte le chiavi Gemini sono temporaneamente in errore "
            "(solitamente per quota superata). Riprova tra qualche minuto."
            + (f"\nUltimo errore: {ultimo_errore[:150]}" if ultimo_errore else "")
        )


ai_router = GeminiRouter()
