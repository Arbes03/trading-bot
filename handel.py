"""Gemeinsame Handelslogik für Live-Bot und Backtest."""

import config
from depot import Depot
from strategie import Motor, kauf_signal, verkauf_grund


def uhrzeit(zeit) -> str:
    return zeit.strftime("%H:%M")


def kaeufe_erlaubt(zeit, depotwert: float, tagesstart: float, motor: Motor) -> bool:
    """Neue Käufe nur zu ruhigen Zeiten und solange das Tagesverlust-Limit nicht erreicht ist."""
    if uhrzeit(zeit) < config.KEINE_KAEUFE_VOR:
        return False
    if motor.nichts_ueber_nacht and uhrzeit(zeit) >= config.ALLES_VERKAUFEN_AB:
        return False
    return depotwert > tagesstart * (1 - config.TAGES_VERLUST_LIMIT)


def notbremse_pruefen(depot: Depot, kurse: dict[str, float], zeit) -> str | None:
    """Fällt das Depot zu weit unter das Startkapital: alles verkaufen und pausieren.

    Gibt eine Meldung zurück, wenn die Notbremse gerade ausgelöst wurde.
    """
    if not config.NOTBREMSE_AB or depot.pausiert:
        return None
    wert = depot.gesamtwert(kurse)
    grenze = config.STARTKAPITAL * (1 - config.NOTBREMSE_AB)
    if wert > grenze:
        return None
    alles_verkaufen(depot, kurse, zeit, "Notbremse", "notbremse",
                    f"Depot bei {wert:,.2f} EUR, unter der Grenze von {grenze:,.2f} EUR "
                    f"(-{config.NOTBREMSE_AB:.0%} vom Startkapital)")
    return f"NOTBREMSE: alles verkauft, Bot pausiert. {depot.pausiert['grund']}"


def wunsch_verkauf_pruefen(depot: Depot, kurse: dict[str, float], zeit) -> str | None:
    """Hast du "alles verkaufen" angefordert (z. B. per Telegram), wird das jetzt ausgeführt."""
    if not depot.verkauf_angefordert:
        return None
    depot.verkauf_angefordert = None
    alles_verkaufen(depot, kurse, zeit, "Auf deinen Wunsch", "wunsch", "Du hast alles verkaufen lassen")
    return f"VERKAUF AUF WUNSCH: alles verkauft, Bot pausiert. Depot: {depot.gesamtwert({}):,.2f} EUR"


def alles_verkaufen(depot: Depot, kurse: dict[str, float], zeit, grund: str, art: str, beschreibung: str):
    """Verkauft alle Positionen und pausiert den Bot (bis zur Freigabe)."""
    for ticker in list(depot.positionen):
        depot.verkaufen(ticker, kurse.get(ticker, depot.positionen[ticker]["einstandskurs"]), zeit, grund)
    depot.pausiert = {"seit": str(zeit)[:16], "grund": beschreibung, "art": art}


def ticker_pruefen(depot: Depot, motor: Motor, ticker: str, letzte: dict, vorletzte: dict,
                   kurs: float, zeit, darf_kaufen: bool, depotwert: float,
                   kurse: dict[str, float] | None = None) -> str | None:
    """Prüft eine Aktie und handelt, falls nötig. Gibt eine Meldung zurück, wenn gehandelt wurde."""
    name = config.WATCHLIST.get(ticker, ticker)

    if ticker in depot.positionen:
        if motor.nichts_ueber_nacht and uhrzeit(zeit) >= config.ALLES_VERKAUFEN_AB:
            grund = "Börsenschluss naht"
        else:
            grund = verkauf_grund(kurs, letzte, vorletzte, depot.positionen[ticker], motor)
        if grund:
            stueck = depot.positionen[ticker]["stueck"]
            gewinn = depot.verkaufen(ticker, kurs, zeit, grund)
            return f"VERKAUF {stueck} x {name} zu {kurs:.2f} EUR | {gewinn:+.2f} EUR | {grund}"
        depot.hoechstkurs_aktualisieren(ticker, kurs)

    elif darf_kaufen and depot.darf_kaufen(ticker, zeit, motor):
        grund = kauf_signal(letzte, vorletzte, motor)
        if not grund:
            return None
        meldungen = []
        # Alle Plätze voll: schwächste Position tauschen, aber nur wenn sie nach Gebühren im Plus ist
        if motor.tauschen and kurse is not None and len(depot.positionen) >= motor.positionen_hoechstens:
            tausch = schwaechste_im_plus(depot, kurse)
            if tausch:
                stueck = depot.positionen[tausch]["stueck"]
                gewinn = depot.verkaufen(tausch, kurse[tausch], zeit, f"Getauscht gegen {name}")
                meldungen.append(f"VERKAUF {stueck} x {config.WATCHLIST.get(tausch, tausch)} zu "
                                 f"{kurse[tausch]:.2f} EUR | {gewinn:+.2f} EUR | Getauscht gegen {name}")
        if depot.kaufen(ticker, kurs, zeit, grund, depotwert, motor):
            stueck = depot.positionen[ticker]["stueck"]
            meldungen.append(f"KAUF    {stueck} x {name} zu {kurs:.2f} EUR | {grund}")
        return "\n".join(meldungen) or None
    return None


def schwaechste_im_plus(depot: Depot, kurse: dict[str, float]) -> str | None:
    """Die Position mit dem kleinsten Gewinn, die nach Spread und Gebühr trotzdem im Plus wäre."""
    kandidaten = {}
    for ticker, pos in depot.positionen.items():
        if ticker not in kurse:
            continue
        erloes = pos["stueck"] * kurse[ticker] * (1 - config.SPREAD / 2) - config.GEBUEHR_PRO_ORDER
        rendite = erloes / pos["kosten"] - 1
        if rendite > 0:
            kandidaten[ticker] = rendite
    return min(kandidaten, key=kandidaten.get) if kandidaten else None
