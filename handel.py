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


def ticker_pruefen(depot: Depot, motor: Motor, ticker: str, letzte: dict, vorletzte: dict,
                   kurs: float, zeit, darf_kaufen: bool, depotwert: float) -> str | None:
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
        if grund and depot.kaufen(ticker, kurs, zeit, grund, depotwert):
            stueck = depot.positionen[ticker]["stueck"]
            return f"KAUF    {stueck} x {name} zu {kurs:.2f} EUR | {grund}"
    return None
