"""Baut die Daten für die Webseite. Lokal (webseite.py) und in der Cloud (cloud_runde.py) gleich."""

from dataclasses import asdict
from datetime import datetime, timedelta

import config
from bot import ZONE, boerse_offen
from depot import trades_lesen, verlauf_lesen
from strategie import aktiver_motor

VERLAUF_PUNKTE = 600


def status_bauen(positionen_roh: dict, bargeld: float, kurse: dict, markt: list, protokoll: list, *,
                 bot_laeuft: bool, letzte_runde: str | None, autostart: bool, backtest: dict,
                 cloud: bool = False, pausiert: dict | None = None,
                 verkauf_angefordert: str | None = None, gewinnkonto: float = 0.0) -> dict:
    positionen = []
    for ticker, pos in positionen_roh.items():
        kurs = kurse.get(ticker) or pos["einstandskurs"]
        positionen.append({
            "ticker": ticker,
            "name": config.WATCHLIST.get(ticker, ticker),
            "gruppe": config.GRUPPE.get(ticker, "Aktie"),
            "stueck": pos["stueck"],
            "einstandskurs": pos["einstandskurs"],
            "investiert": pos["kosten"],  # Kaufpreis inklusive Gebühr
            "kurs": kurs,
            "wert": pos["stueck"] * kurs,
            "gewinn": pos["stueck"] * kurs - pos["kosten"],
            "prozent": kurs / pos["einstandskurs"] - 1,
            "kaufzeit": pos["kaufzeit"][:16],
        })
    depotwert = bargeld + sum(p["wert"] for p in positionen) + gewinnkonto

    trades = trades_lesen(config.TRADES_DATEI)
    gewinne = [float(t["gewinn"]) for t in trades if t["art"] == "VERKAUF"]
    verlauf = verlauf_lesen(config.VERLAUF_DATEI)
    schritt = max(1, len(verlauf) // VERLAUF_PUNKTE)

    jetzt = datetime.now(ZONE)
    # Tagesergebnis: Vergleich mit dem letzten Depotwert vor heute
    heute = f"{jetzt:%Y-%m-%d}"
    tagesstart = wert_vor(verlauf, heute)
    wochenstart = wert_vor(verlauf, f"{jetzt - timedelta(days=jetzt.weekday()):%Y-%m-%d}")  # seit Montag
    monatsstart = wert_vor(verlauf, f"{jetzt:%Y-%m}-01")
    realisiert_heute = sum(float(t["gewinn"]) for t in trades
                           if t["art"] == "VERKAUF" and t["zeit"][:10] == heute)
    return {
        "jetzt": f"{jetzt:%d.%m.%Y %H:%M}",
        "cloud": cloud,
        "bot_laeuft": bot_laeuft,
        "autostart": autostart,
        "notbremse": {
            "aktiv": bool(pausiert),
            "seit": pausiert["seit"] if pausiert else None,
            "grund": pausiert["grund"] if pausiert else None,
            "art": (pausiert or {}).get("art", "notbremse"),
            "verkauf_angefordert": verkauf_angefordert,
            "grenze": config.STARTKAPITAL * (1 - config.NOTBREMSE_AB) if config.NOTBREMSE_AB else None,
            "prozent": config.NOTBREMSE_AB,
        },
        "boerse_offen": boerse_offen(jetzt),
        "letzte_runde": letzte_runde,
        "startkapital": config.STARTKAPITAL,
        "depotwert": depotwert,
        "bargeld": bargeld,           # Handelsgeld (damit kauft der Bot)
        "gewinnkonto": gewinnkonto,   # gesicherte Gewinne, werden nicht investiert
        "positionen": positionen,
        "ergebnis": {
            "gesamt": depotwert - config.STARTKAPITAL,
            "heute": depotwert - tagesstart,
            "heute_prozent": depotwert / tagesstart - 1,
            "woche": depotwert - wochenstart,
            "woche_prozent": depotwert / wochenstart - 1,
            "monat": depotwert - monatsstart,
            "monat_prozent": depotwert / monatsstart - 1,
            "offen": sum(p["gewinn"] for p in positionen),
            "realisiert": sum(gewinne),
            "realisiert_heute": realisiert_heute,
        },
        "markt": markt,
        "trades": list(reversed(trades[-100:])),
        "verkaeufe": verkaeufe_auswerten(trades),
        "tage": tagesergebnisse(verlauf, heute, depotwert),
        "vergleich": {
            "name": config.WATCHLIST.get(config.VERGLEICH_ETF, config.VERGLEICH_ETF),
            "wert": next((v["halten"] for v in reversed(verlauf) if v.get("halten")), None),
        },
        "statistik": {
            "anzahl": len(gewinne),
            "gewinn_trades": sum(g > 0 for g in gewinne),
            "summe": sum(gewinne),
            "gebuehren": len(trades) * config.GEBUEHR_PRO_ORDER,
        },
        "verlauf": verlauf[::schritt] + ([verlauf[-1]] if verlauf and (len(verlauf) - 1) % schritt else []),
        "protokoll": protokoll,
        "einstellungen": {
            "watchlist": list(config.WATCHLIST.values()),
            "motor": asdict(aktiver_motor()),
            "motoren": [{"name": n, "titel": m["titel"], "beschreibung": m["beschreibung"]}
                        for n, m in config.MOTOREN.items()],
            "max_anteil": config.MAX_ANTEIL_PRO_POSITION,
            "max_positionen": config.MAX_POSITIONEN,
            "tages_limit": config.TAGES_VERLUST_LIMIT,
            "gebuehr": config.GEBUEHR_PRO_ORDER,
            "boerse": f"Mo-Fr {config.BOERSE_AUF}-{config.BOERSE_ZU}",
            "alles_verkaufen_ab": config.ALLES_VERKAUFEN_AB,
        },
        "backtest": backtest,
        "nachrichten": nachrichten_status(),
    }


def wert_vor(verlauf: list[dict], datum: str) -> float:
    """Letzter Depotwert vor diesem Datum (JJJJ-MM-TT), sonst das Startkapital."""
    vorher = [v["wert"] for v in verlauf if v["zeit"][:10] < datum]
    return vorher[-1] if vorher else config.STARTKAPITAL


def tagesergebnisse(verlauf: list[dict], heute: str, depotwert: float, tage: int = 120) -> list[dict]:
    """Gewinn/Verlust jedes Tages (Schlusswert minus Schlusswert des Vortags), für den Kalender."""
    schluss: dict[str, float] = {}
    for v in verlauf:
        schluss[v["zeit"][:10]] = v["wert"]
    schluss[heute] = depotwert  # heute mit dem aktuellen Wert
    ergebnisse, vorher = [], config.STARTKAPITAL
    for datum in sorted(schluss):
        ergebnisse.append({"datum": datum, "wert": schluss[datum], "gv": schluss[datum] - vorher})
        vorher = schluss[datum]
    return ergebnisse[-tage:]


def verkaeufe_auswerten(trades: list[dict]) -> list[dict]:
    """Jeder Verkauf mit dem passenden Kauf davor: wann gekauft, zu welchem Preis, wie lange gehalten."""
    letzter_kauf: dict[str, dict] = {}
    verkaeufe = []
    for t in trades:  # trades.csv ist zeitlich sortiert
        if t["art"] == "KAUF":
            letzter_kauf[t["ticker"]] = t
            continue
        kauf = letzter_kauf.pop(t["ticker"], None)
        stueck = float(t["stueck"])  # Krypto kann Bruchteile haben
        gewinn = float(t["gewinn"])
        erloes = stueck * float(t["kurs"]) - config.GEBUEHR_PRO_ORDER
        investiert = erloes - gewinn
        tage = None
        if kauf:
            tage = (datetime.fromisoformat(t["zeit"]) - datetime.fromisoformat(kauf["zeit"])).total_seconds() / 86400
        verkaeufe.append({
            "ticker": t["ticker"],
            "name": config.WATCHLIST.get(t["ticker"], t["ticker"]),
            "gruppe": config.GRUPPE.get(t["ticker"], "Aktie"),
            "stueck": stueck,
            "kaufzeit": kauf["zeit"] if kauf else None,
            "kaufkurs": float(kauf["kurs"]) if kauf else None,
            "verkaufzeit": t["zeit"],
            "verkaufkurs": float(t["kurs"]),
            "investiert": investiert,
            "erloes": erloes,
            "gewinn": gewinn,
            "prozent": gewinn / investiert if investiert else 0,
            "tage": tage,
            "grund": t["grund"],
        })
    return verkaeufe


def nachrichten_status() -> dict:
    """Stand der Handy-Nachrichten aus benachrichtigung.json (enthält keine Zugangsdaten)."""
    import json
    import os
    if not os.path.exists(config.BENACHRICHTIGUNG_DATEI):
        return {}
    with open(config.BENACHRICHTIGUNG_DATEI, encoding="utf-8") as f:
        return json.load(f)
