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
from benachrichtigung import (eingerichtet, notbremse_melden, senden, stand_melden, tagesabschluss_melden,
                              telegram_befehle_holen, trade_melden, willkommen_melden, wunsch_verkauf_melden)
from bot import ZONE, boerse_offen, runde
from handel import uhrzeit
from daten import fuer_alle, marktueberblick
from depot import Depot, verlauf_lesen
from strategie import aktiver_motor
from uebersicht import status_bauen

FREIGABE_DATEI = "notbremse_aufheben.txt"
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

    gemerkt = gemerktes_laden()

    # Freigabe nach der Notbremse: Datei notbremse_aufheben.txt bei GitHub anlegen
    if os.path.exists(FREIGABE_DATEI):
        os.remove(FREIGABE_DATEI)
        if depot.pausiert:
            weiter_handeln(depot, melden)

    # Deine Befehle aus Telegram (/verkaufen, /weiter, /stand, /hilfe)
    befehle, gemerkt["telegram_offset"] = telegram_befehle_holen(gemerkt.get("telegram_offset", 0))
    stand_gewuenscht = False
    for befehl in befehle:
        stand_gewuenscht |= befehl_ausfuehren(befehl, depot, jetzt, melden)

    kurse: dict[str, float] = {}
    if boerse_offen(jetzt):
        motor = aktiver_motor()
        kurse, meldungen, anzahl = runde(depot, motor, tagesstart_ermitteln(jetzt))
        for m in meldungen:
            melden(m)
        melden(f"Prüfrunde fertig ({motor.titel}): Depot {depot.gesamtwert(kurse):,.2f} EUR, "
               f"Kurse für {anzahl}/{len(config.WATCHLIST)} Werte")
        # Bei einem Komplett-Verkauf eine Sammelmeldung statt vieler einzelner
        if any(m.startswith("VERKAUF AUF WUNSCH") for m in meldungen):
            wunsch_verkauf_melden(depot.trades, depot.gesamtwert(kurse))
        elif any(m.startswith("NOTBREMSE") for m in meldungen):
            notbremse_melden(depot.pausiert, depot.gesamtwert(kurse))
        elif config.NACHRICHT_BEI_TRADES:
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
        pausiert=depot.pausiert,
        verkauf_angefordert=depot.verkauf_angefordert,
    )
    os.makedirs(AUSGABE_ORDNER, exist_ok=True)
    with open(os.path.join(AUSGABE_ORDNER, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, default=str)
    shutil.copy(os.path.join("web", "index.html"), os.path.join(AUSGABE_ORDNER, "index.html"))
    print(f"Webseiten-Daten geschrieben: {AUSGABE_ORDNER}/status.json")

    if stand_gewuenscht:
        stand_melden(status, f"{jetzt:%Y-%m-%d}")
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


BEFEHLE_VERKAUFEN = {"/verkaufen", "verkaufen", "alles verkaufen", "/raus", "raus"}
BEFEHLE_WEITER = {"/weiter", "weiter"}
BEFEHLE_STAND = {"/stand", "stand"}
HILFE = ("Das kannst du mir schreiben:\n"
         "/verkaufen – ich verkaufe alle Aktien und pausiere\n"
         "/weiter – ich handle wieder nach meinen Regeln\n"
         "/stand – ich schicke dir den aktuellen Stand\n"
         "/hilfe – diese Übersicht\n\n"
         "Ich schaue Mo–Fr während der Börsenzeit etwa alle 15–40 Minuten nach neuen Nachrichten.")


def befehl_ausfuehren(befehl: str, depot: Depot, jetzt: datetime, melden) -> bool:
    """Führt einen Telegram-Befehl aus. Gibt True zurück, wenn der Stand geschickt werden soll."""
    wort = befehl.split("@")[0]  # "/verkaufen@Trading_arbes_bot" -> "/verkaufen"
    if wort in BEFEHLE_VERKAUFEN:
        if not depot.positionen:
            senden("Nichts zu verkaufen", "Ich habe gerade keine Aktien. Alles liegt als Bargeld bereit.")
            return False
        depot.verkauf_angefordert = f"{jetzt:%Y-%m-%d %H:%M}"
        depot.speichern()
        melden("Verkauf aller Aktien per Telegram angefordert.")
        if boerse_offen(jetzt):
            senden("👍 Verstanden: Ich verkaufe jetzt alles", "Die Bestätigung kommt gleich.")
        else:
            senden("👍 Verstanden: Ich verkaufe alles, sobald die Börse öffnet",
                   "Die Börse ist gerade geschlossen (Mo–Fr 9:00–17:30 Uhr). Danach pausiere ich, "
                   "bis du /weiter schreibst. Abbrechen: /weiter")
    elif wort in BEFEHLE_WEITER:
        if depot.pausiert or depot.verkauf_angefordert:
            weiter_handeln(depot, melden)
        else:
            senden("Läuft schon", "Ich bin nicht pausiert und handle ganz normal.")
    elif wort in BEFEHLE_STAND:
        return True
    else:
        senden("Hallo! 👋", HILFE)
    return False


def weiter_handeln(depot: Depot, melden):
    """Pause bzw. angeforderten Verkauf aufheben."""
    depot.pausiert = None
    depot.verkauf_angefordert = None
    depot.speichern()
    melden("Pause aufgehoben, der Bot handelt wieder.")
    senden("✅ Weiter geht's", "Ich handle ab jetzt wieder nach meinen Regeln.", tags=["white_check_mark"])


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
