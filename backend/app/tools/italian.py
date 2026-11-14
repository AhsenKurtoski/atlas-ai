"""
Modulo italiano per ATLAS AI v3.0.

Contenuti reali (lezioni + quiz) usati sia dai tool dell'AI sia dagli endpoint
`/italiano/*` che alimentano la schermata Italiano dell'app.

Nessuna generazione casuale "inventata": la lezione del giorno è deterministica
(data → indice) così tutti i membri della famiglia vedono la stessa lezione.
"""
from __future__ import annotations

import datetime
from typing import Any

LIVELLI = ("A1", "A2", "B1", "B2", "C1")

LEZIONI: dict[str, list[dict[str, Any]]] = {
    "A1": [
        {
            "id": "a1-presente-essere",
            "titolo": "Il presente di essere e avere",
            "spiegazione": (
                "I verbi essere e avere sono i più usati. Al presente: io sono, tu sei, "
                "lui/lei è, noi siamo, voi siete, loro sono. Avere: io ho, tu hai, lui/lei ha, "
                "noi abbiamo, voi avete, loro hanno. Servono per presentarsi e per formare i tempi composti."
            ),
            "esempi": [
                "Io sono albanese e vivo in Italia.",
                "Tu hai una famiglia numerosa.",
                "Noi siamo a casa alle sette.",
            ],
            "esercizio": "Completa: «Io ___ (essere) a scuola e tu ___ (avere) fame.»",
        },
        {
            "id": "a1-articoli",
            "titolo": "Articoli determinativi e indeterminativi",
            "spiegazione": (
                "Maschile singolare: il / lo / l' e un / uno. Femminile singolare: la / l' e una / un'. "
                "Plurale: i, gli, le. Si usa «lo» prima di s+consonante, z, gn, ps; «l'» davanti a vocale."
            ),
            "esempi": ["lo studente, gli studenti", "la scuola, le scuole", "un'amica, un amico"],
            "esercizio": "Scegli l'articolo: ___ zaino, ___ amica, ___ libri.",
        },
    ],
    "A2": [
        {
            "id": "a2-passato-prossimo",
            "titolo": "Il passato prossimo",
            "spiegazione": (
                "Si forma con avere o essere + participio passato. Con essere il participio concorda "
                "con il soggetto (andato/andata). Esempi: ho mangiato, sono andato, siamo partiti."
            ),
            "esempi": [
                "Ieri ho comprato il pane.",
                "Mamma è andata al mercato.",
                "Abbiamo visto un film insieme.",
            ],
            "esercizio": "Trasforma al passato prossimo: «Vado al lavoro» → «___».",
        },
        {
            "id": "a2-preposizioni",
            "titolo": "Preposizioni di luogo",
            "spiegazione": (
                "In, a, da, su, sotto, davanti a, dietro, accanto a. Con i nomi di città si usa «a» "
                "(a Milano), con i paesi «in» (in Italia). «Da» indica provenienza o permanenza."
            ),
            "esempi": ["Vivo a Roma, in Italia.", "Vengo da Tirana.", "Il gatto è sotto il tavolo."],
            "esercizio": "Completa: «Domani vado ___ Napoli e resto ___ mia sorella.»",
        },
    ],
    "B1": [
        {
            "id": "b1-condizionale",
            "titolo": "Il condizionale presente",
            "spiegazione": (
                "Si usa per chiedere in modo gentile, esprimere un desiderio o un'ipotesi. "
                "Vorrei, potrei, dovrei, farei, andrei. È il tempo delle buone maniere: "
                "«Vorrei un caffè» è più educato di «Voglio un caffè»."
            ),
            "esempi": [
                "Vorrei prenotare una visita per mia madre.",
                "Potresti ripetere più lentamente, per favore?",
                "Sarebbe meglio partire prima delle otto.",
            ],
            "esercizio": "Rendi gentile la frase: «Voglio parlare con il medico» → «___».",
        },
        {
            "id": "b1-pronomi",
            "titolo": "Pronomi diretti e indiretti",
            "spiegazione": (
                "Diretti: mi, ti, lo, la, ci, vi, li, le (rispondono a «chi? che cosa?»). "
                "Indiretti: mi, ti, gli, le, ci, vi, gli (rispondono a «a chi?»). "
                "Al passato prossimo il participio concorda con i pronomi diretti: «Le ho comprate»."
            ),
            "esempi": ["Il pane lo compro io.", "A mamma le ho telefonato ieri.", "Li ho invitati a cena."],
            "esercizio": "Sostituisci: «Ho chiamato mia sorella» → «___ ho chiamata».",
        },
    ],
    "B2": [
        {
            "id": "b2-congiuntivo",
            "titolo": "Il congiuntivo presente",
            "spiegazione": (
                "Dopo verbi di opinione, desiderio e speranza si usa il congiuntivo: "
                "penso che sia, spero che venga, è importante che tu capisca. "
                "Le forme di essere: sia, sia, sia, siamo, siate, siano."
            ),
            "esempi": [
                "Penso che sia una buona idea.",
                "Spero che i ragazzi arrivino presto.",
                "È importante che voi parliate italiano ogni giorno.",
            ],
            "esercizio": "Completa: «Credo che lui ___ (avere) ragione.»",
        },
        {
            "id": "b2-periodo-ipotetico",
            "titolo": "Periodo ipotetico del secondo tipo",
            "spiegazione": (
                "Ipotesi improbabile: «se + congiuntivo imperfetto, condizionale presente». "
                "Esempio: «Se avessi più tempo, studierei di più». Non si usa il condizionale "
                "nella frase con «se»."
            ),
            "esempi": [
                "Se potessi, verrei subito.",
                "Se avessimo una macchina, andremmo al mare.",
            ],
            "esercizio": "Completa: «Se tu ___ (studiare) di più, ___ (superare) l'esame.»",
        },
    ],
    "C1": [
        {
            "id": "c1-congiuntivo-passato",
            "titolo": "Congiuntivo passato e trapassato",
            "spiegazione": (
                "Congiuntivo passato: «che io abbia fatto». Trapassato: «che io avessi fatto». "
                "Servono per esprimere anteriorità rispetto al verbo principale: "
                "«Penso che abbia già mangiato»."
            ),
            "esempi": [
                "Credo che siano già partiti.",
                "Non sapevo che tu avessi studiato il cinese.",
            ],
            "esercizio": "Completa: «Immagino che voi ___ (finire) già il lavoro.»",
        },
        {
            "id": "c1-connettivi",
            "titolo": "Connettivi e registro formale",
            "spiegazione": (
                "Per un italiano accurato: «tuttavia, pertanto, inoltre, affinché, purché, "
                "nonostante». Nel parlato informale si semplifica, nello scritto formale "
                "si preferiscono i connettivi espliciti."
            ),
            "esempi": [
                "La richiesta è stata accolta; pertanto non serve inviare altro.",
                "Nonostante la pioggia, siamo usciti.",
                "Ti scrivo affinché tu possa preparare i documenti.",
            ],
            "esercizio": "Unisci con un connettivo: «Ha studiato molto. Ha superato l'esame.»",
        },
    ],
}

QUIZ: list[dict[str, Any]] = [
    {
        "id": "q01",
        "livello": "A1",
        "domanda": "Quale articolo completa «___ amica»?",
        "opzioni": ["un", "un'", "una", "il"],
        "risposta": 1,
        "spiegazione": "Davanti a vocale femminile si usa l'apostrofo: un'amica.",
    },
    {
        "id": "q02",
        "livello": "A1",
        "domanda": "Completa: «Noi ___ italiani.»",
        "opzioni": ["è", "siamo", "siete", "sono"],
        "risposta": 1,
        "spiegazione": "Noi siamo è la prima persona plurale del verbo essere.",
    },
    {
        "id": "q03",
        "livello": "A1",
        "domanda": "Quale è il plurale di «lo studente»?",
        "opzioni": ["i studenti", "gli studenti", "le studenti", "li studenti"],
        "risposta": 1,
        "spiegazione": "Davanti a s+consonante al plurale si usa gli: gli studenti.",
    },
    {
        "id": "q04",
        "livello": "A2",
        "domanda": "Completa: «Ieri ___ andata al mercato.» (riferito a mamma)",
        "opzioni": ["ho", "ha", "è", "sono"],
        "risposta": 2,
        "spiegazione": "Con i verbi di movimento si usa essere: è andata.",
    },
    {
        "id": "q05",
        "livello": "A2",
        "domanda": "Quale frase è corretta?",
        "opzioni": ["Vivo a Italia", "Vivo in Italia", "Vivo da Italia", "Vivo su Italia"],
        "risposta": 1,
        "spiegazione": "Con i nomi di paese si usa in: in Italia.",
    },
    {
        "id": "q06",
        "livello": "A2",
        "domanda": "Quale è il passato prossimo di «vedere»?",
        "opzioni": ["ho veduto", "ho visto", "sono visto", "avevo visto"],
        "risposta": 1,
        "spiegazione": "Il participio passato di vedere è visto: ho visto.",
    },
    {
        "id": "q07",
        "livello": "B1",
        "domanda": "Quale forma è più gentile?",
        "opzioni": ["Voglio un caffè.", "Vorrei un caffè.", "Dammi un caffè.", "Ho un caffè."],
        "risposta": 1,
        "spiegazione": "Il condizionale (vorrei) rende la richiesta cortese.",
    },
    {
        "id": "q08",
        "livello": "B1",
        "domanda": "Completa: «A mia madre ___ ho telefonato ieri.»",
        "opzioni": ["la", "le", "gli", "li"],
        "risposta": 2,
        "spiegazione": "Il pronome indiretto per lei è le: a mia madre le.",
    },
    {
        "id": "q09",
        "livello": "B1",
        "domanda": "Quale è il condizionale di «potere»?",
        "opzioni": ["posso", "potrei", "potessi", "potrò"],
        "risposta": 1,
        "spiegazione": "Potrei è il condizionale presente di potere.",
    },
    {
        "id": "q10",
        "livello": "B2",
        "domanda": "Completa: «Penso che lui ___ ragione.»",
        "opzioni": ["ha", "abbia", "avrebbe", "avesse"],
        "risposta": 1,
        "spiegazione": "Dopo «penso che» serve il congiuntivo: abbia.",
    },
    {
        "id": "q11",
        "livello": "B2",
        "domanda": "Quale frase è corretta?",
        "opzioni": [
            "Se avrei tempo, studierei.",
            "Se avessi tempo, studierei.",
            "Se avessi tempo, studierei se.",
            "Se ho tempo, studierei.",
        ],
        "risposta": 1,
        "spiegazione": "Secondo tipo: se + congiuntivo imperfetto, condizionale presente.",
    },
    {
        "id": "q12",
        "livello": "B2",
        "domanda": "Completa: «Non sapevo che tu ___ a Roma.»",
        "opzioni": ["sei", "fossi", "sarai", "sarebbe"],
        "risposta": 1,
        "spiegazione": "Al passato il congiuntivo imperfetto esprime contemporaneità: fossi.",
    },
    {
        "id": "q13",
        "livello": "C1",
        "domanda": "Completa: «Immagino che voi ___ già il lavoro.»",
        "opzioni": ["avete finito", "abbiate finito", "avevate finito", "finireste"],
        "risposta": 1,
        "spiegazione": "Congiuntivo passato: abbiate finito.",
    },
    {
        "id": "q14",
        "livello": "C1",
        "domanda": "Quale connettivo esprime conseguenza?",
        "opzioni": ["purché", "pertanto", "affinché", "nonostante"],
        "risposta": 1,
        "spiegazione": "Pertanto introduce una conseguenza logica.",
    },
    {
        "id": "q15",
        "livello": "C1",
        "domanda": "Completa: «Ti scrivo affinché tu ___ i documenti.»",
        "opzioni": ["prepari", "preparerai", "preparavi", "prepareresti"],
        "risposta": 0,
        "spiegazione": "Affinché richiede il congiuntivo: prepari.",
    },
]


def normalizza_livello(livello: str | None) -> str:
    value = (livello or "B1").strip().upper()
    return value if value in LIVELLI else "B1"


def lezione_del_giorno(livello: str | None = None, giorno: datetime.date | None = None) -> dict[str, Any]:
    """Lezione deterministica del giorno per il livello richiesto."""
    livello_norm = normalizza_livello(livello)
    lezioni = LEZIONI.get(livello_norm) or LEZIONI["B1"]
    data = giorno or datetime.date.today()
    lezione = dict(lezioni[data.toordinal() % len(lezioni)])
    lezione["livello"] = livello_norm
    lezione["data"] = data.isoformat()
    return lezione


def quiz_per_livello(livello: str | None = None, quantita: int = 5) -> list[dict[str, Any]]:
    """Quiz del giorno: domande del livello richiesto (fallback su altri livelli)."""
    livello_norm = normalizza_livello(livello)
    quantita = max(1, min(int(quantita or 5), len(QUIZ)))
    ordine = {lv: i for i, lv in enumerate(LIVELLI)}
    ordinato = sorted(QUIZ, key=lambda q: (abs(ordine[q["livello"]] - ordine[livello_norm]), q["id"]))
    return ordinato[:quantita]


def valuta_quiz(risposte: list[dict[str, Any]]) -> dict[str, Any]:
    """Valuta le risposte inviate dal client (id domanda + indice scelta)."""
    by_id = {q["id"]: q for q in QUIZ}
    corrette = 0
    dettaglio: list[dict[str, Any]] = []
    for risposta in risposte:
        domanda = by_id.get(str(risposta.get("id", "")))
        if not domanda:
            continue
        scelta = risposta.get("scelta")
        try:
            scelta_int = int(scelta)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            scelta_int = -1
        giusta = scelta_int == domanda["risposta"]
        if giusta:
            corrette += 1
        dettaglio.append(
            {
                "id": domanda["id"],
                "corretta": giusta,
                "risposta_giusta": domanda["opzioni"][domanda["risposta"]],
                "spiegazione": domanda["spiegazione"],
            }
        )
    totale = len(dettaglio)
    return {
        "corrette": corrette,
        "totale": totale,
        "punteggio": corrette * 10,
        "percentuale": round((corrette / totale) * 100, 1) if totale else 0.0,
        "dettaglio": dettaglio,
    }


def testi_per_livello(livello: str | None = None) -> list[dict[str, Any]]:
    """Elenco lezioni (senza contenuto) per il livello."""
    livello_norm = normalizza_livello(livello)
    return [
        {"id": lezione["id"], "titolo": lezione["titolo"]}
        for lezione in LEZIONI.get(livello_norm, LEZIONI["B1"])
    ]


def lezione_italiano(livello: str = "B1") -> str:
    """Spiega la lezione di italiano del giorno, adatta al livello indicato.

    Args:
        livello: Livello del profilo: A1, A2, B1, B2 o C1.
    """
    lezione = lezione_del_giorno(livello)
    esempi = "\n".join(f"  • {frase}" for frase in lezione["esempi"])
    return (
        f"🇮🇹 Lezione di oggi · {lezione['livello']}\n"
        f"**{lezione['titolo']}**\n\n"
        f"{lezione['spiegazione']}\n\n"
        f"Esempi:\n{esempi}\n\n"
        f"✏️ Esercizio: {lezione['esercizio']}"
    )
