"""Kursdaten von Yahoo Finance (kostenlos, ohne Anmeldung).

Jede Kerze ist ein dict: {"zeit": datetime, "close": float, ...Indikatoren}.
"""

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from strategie import Motor, indikatoren_berechnen, motor_laden

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={zeitraum}&interval={intervall}"
ZONE = ZoneInfo(config.ZEITZONE)


def kurse_laden(ticker: str, zeitraum: str, motor: Motor) -> list[dict]:
    url = URL.format(ticker=ticker, zeitraum=zeitraum, intervall=motor.intervall)
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        ergebnis = json.load(antwort)["chart"]["result"]
    if not ergebnis or "timestamp" not in ergebnis[0]:
        return []

    zeiten = ergebnis[0]["timestamp"]
    schlusskurse = ergebnis[0]["indicators"]["quote"][0]["close"]
    kerzen = [{"zeit": datetime.fromtimestamp(t, ZONE), "close": c}
              for t, c in zip(zeiten, schlusskurse) if c is not None]
    return indikatoren_berechnen(kerzen, motor)


def fuer_alle(funktion, ticker_liste) -> tuple[dict, dict]:
    """Ruft `funktion(ticker)` für viele Werte gleichzeitig auf (schneller als nacheinander).

    Gibt (Ergebnisse, Fehler) als zwei dicts ticker -> Wert zurück.
    """
    def sicher(ticker):
        try:
            return ticker, funktion(ticker), None
        except Exception as fehler:
            return ticker, None, fehler

    ergebnisse, fehler = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for ticker, wert, f in pool.map(sicher, ticker_liste):
            if f is not None:
                fehler[ticker] = f
            elif wert:
                ergebnisse[ticker] = wert
    return ergebnisse, fehler


def marktueberblick(ticker: str) -> dict | None:
    """Kurs, Tagesveränderung, Kurztrend und Tagesverlauf einer Aktie für die Übersicht."""
    # Für die Übersicht immer 5-Minuten-Kerzen: zeigt den Tagesverlauf am besten
    kerzen = kurse_laden(ticker, "5d", motor_laden("schnell"))
    if len(kerzen) < 3:
        return None
    letzter_tag = kerzen[-1]["zeit"].date()
    heute = [k for k in kerzen if k["zeit"].date() == letzter_tag]
    vortag = [k for k in kerzen if k["zeit"].date() < letzter_tag]
    vortag_schluss = vortag[-1]["close"] if vortag else heute[0]["close"]
    letzte = kerzen[-1]
    return {
        "ticker": ticker,
        "name": config.WATCHLIST.get(ticker, ticker),
        "gruppe": config.GRUPPE.get(ticker, "Aktie"),
        "kurs": letzte["close"],
        "stand": f"{letzte['zeit']:%d.%m. %H:%M}",
        "vortag_schluss": vortag_schluss,
        "veraenderung": letzte["close"] / vortag_schluss - 1,
        "trend": "auf" if letzte["ema_kurz"] > letzte["ema_lang"] else "ab",
        "rsi": letzte["rsi"],
        "verlauf": [{"zeit": f"{k['zeit']:%H:%M}", "kurs": k["close"]} for k in heute],
    }
