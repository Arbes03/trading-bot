"""Eine einzelne Prüfrunde für GitHub (läuft dort alle 15 Minuten, auch wenn dein PC aus ist).

Aufruf:  python cloud_runde.py
Speichert den neuen Stand in depot.json, trades.csv, verlauf.csv und protokoll.json
und legt die Webseite samt Daten im Ordner public/ ab (wird von GitHub Pages veröffentlicht).
"""

import json
import os
import shutil
from datetime import datetime

import benachrichtigung
import config
from benachrichtigung import eingerichtet, tagesabschluss_melden, trade_melden, willkommen_melden
from bot import ZONE, boerse_offen, runde
from handel import uhrzeit
from daten import fuer_alle, marktueberblick
from depot import Depot, verlauf_lesen
from strategie import aktiver_motor
from uebersicht import status_bauen

PROTOKOLL_DATEI = "protokoll.json"
PROTOKOLL_MAX = 200
AUSGABE_ORDNER = "public"


def protokoll_laden() -> list[dict]:
    if not os.path.exists(PROTOKOLL_DATEI):
        return []
    with open(PROTOKOLL_DATEI, encoding="utf-8") as f:
        return json.load(f)


def tagesstart_ermitteln(jetzt: datetime) -> float:
    """Depotwert zum Ende des letzten Handelstags (für das Tagesverlust-Limit)."""
    heute = f"{jetzt:%Y-%m-%d}"
    vor_heute = [v["wert"] for v in verlauf_lesen(config.VERLAUF_DATEI) if v["zeit"][:10] < heute]
    return vor_heute[-1] if vor_heute else config.STARTKAPITAL


def main():
    jetzt = datetime.now(ZONE)
    depot = Depot(config.DEPOT_DATEI, config.TRADES_DATEI)
    protokoll = protokoll_laden()

    def melden(text: str):
        protokoll.insert(0, {"zeit": f"{jetzt:%d.%m. %H:%M}", "text": text})
        print(text)

    kurse: dict[str, float] = {}
    if boerse_offen(jetzt):
        motor = aktiver_motor()
        kurse, meldungen, anzahl = runde(depot, motor, tagesstart_ermitteln(jetzt))
        for m in meldungen:
            melden(m)
        melden(f"Prüfrunde fertig ({motor.titel}): Depot {depot.gesamtwert(kurse):,.2f} EUR, "
               f"Kurse für {anzahl}/{len(config.WATCHLIST)} Werte")
        if config.NACHRICHT_BEI_TRADES:
            for trade in depot.trades:  # nur die Trades dieser Runde
                trade_melden(trade, depot.gesamtwert(kurse))
    else:
        print("Börse geschlossen, keine Prüfrunde.")

    markt, fehler = fuer_alle(marktueberblick, config.WATCHLIST)
    if fehler:
        print(f"Marktdaten nicht geladen für: {', '.join(fehler)}")
    for ticker in depot.positionen:
        if ticker not in kurse and ticker in markt:
            kurse[ticker] = markt[ticker]["kurs"]

    with open(PROTOKOLL_DATEI, "w", encoding="utf-8") as f:
        json.dump(protokoll[:PROTOKOLL_MAX], f, ensure_ascii=False, indent=1)

    status = status_bauen(
        depot.positionen, depot.bargeld, kurse,
        markt=[markt[t] for t in config.WATCHLIST if t in markt],
        protokoll=protokoll[:PROTOKOLL_MAX],
        bot_laeuft=True,
        letzte_runde=f"{jetzt:%d.%m. %H:%M}",
        autostart=False,
        backtest={"laeuft": False, "motor": None, "fehler": None},
        cloud=True,
    )
    os.makedirs(AUSGABE_ORDNER, exist_ok=True)
    with open(os.path.join(AUSGABE_ORDNER, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, default=str)
    shutil.copy(os.path.join("web", "index.html"), os.path.join(AUSGABE_ORDNER, "index.html"))
    print(f"Webseiten-Daten geschrieben: {AUSGABE_ORDNER}/status.json")

    gemerkt = gemerktes_laden()
    wege = eingerichtet()
    print(f"Handy-Nachrichten eingerichtet: {wege or 'keine'}")
    # Einmalig, sobald ein Nachrichtenweg neu eingerichtet ist: Willkommens-Nachricht als Test
    if wege and gemerkt.get("willkommen") != wege and willkommen_melden(status, wege):
        gemerkt["willkommen"] = wege
        print(f"Willkommens-Nachricht gesendet ({wege}).")
    if config.NACHRICHT_TAGESABSCHLUSS:
        tagesabschluss_pruefen(jetzt, status, gemerkt)
    # Zur Kontrolle (ohne Zugangsdaten): welche Wege eingerichtet sind und der letzte Fehler
    gemerkt["eingerichtet"] = wege or "keine"
    if benachrichtigung.letzter_fehler:
        gemerkt["letzter_fehler"] = f"{jetzt:%d.%m. %H:%M}: {benachrichtigung.letzter_fehler}"
    with open(config.BENACHRICHTIGUNG_DATEI, "w", encoding="utf-8") as f:
        json.dump(gemerkt, f)


def gemerktes_laden() -> dict:
    if not os.path.exists(config.BENACHRICHTIGUNG_DATEI):
        return {}
    with open(config.BENACHRICHTIGUNG_DATEI, encoding="utf-8") as f:
        return json.load(f)


def tagesabschluss_pruefen(jetzt: datetime, status: dict, gemerkt: dict):
    """Einmal pro Handelstag nach Börsenschluss eine Zusammenfassung aufs Handy."""
    heute = f"{jetzt:%Y-%m-%d}"
    if not eingerichtet() or jetzt.weekday() >= 5 or uhrzeit(jetzt) < config.BOERSE_ZU:
        return
    if not any(v["zeit"][:10] == heute for v in verlauf_lesen(config.VERLAUF_DATEI)):
        return  # heute keine Prüfrunde gelaufen (z. B. Feiertag)
    if gemerkt.get("tagesabschluss") == heute:
        return
    tagesabschluss_melden(status, heute)
    gemerkt["tagesabschluss"] = heute
    print("Tagesabschluss gesendet.")


if __name__ == "__main__":
    main()
