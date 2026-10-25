"""Zeigt den aktuellen Stand des Spielgeld-Depots und die bisherigen Trades.

Aufruf:  python status.py
"""

import csv
import os

import config
from daten import kurse_laden
from depot import Depot
from strategie import motor_laden


def main():
    depot = Depot(config.DEPOT_DATEI)
    kurse = {}
    for ticker in depot.positionen:
        kerzen = kurse_laden(ticker, "1d", motor_laden("schnell"))
        if kerzen:
            kurse[ticker] = kerzen[-1]["close"]

    wert = depot.gesamtwert(kurse)
    print("=" * 60)
    print(f" Depotwert:  {wert:>12,.2f} EUR  ({wert - config.STARTKAPITAL:+,.2f} EUR, "
          f"{wert / config.STARTKAPITAL - 1:+.2%})")
    print(f" Bargeld:    {depot.bargeld:>12,.2f} EUR")
    print("=" * 60)
    for ticker, pos in depot.positionen.items():
        kurs = kurse.get(ticker, pos["einstandskurs"])
        print(f" {config.WATCHLIST.get(ticker, ticker):<30} {pos['stueck']:>4} Stk. "
              f"{kurs:>8.2f} EUR  {kurs / pos['einstandskurs'] - 1:+.2%}")

    if not os.path.exists(config.TRADES_DATEI):
        print("\n Noch keine Trades.")
        return
    with open(config.TRADES_DATEI, encoding="utf-8-sig") as f:
        trades = list(csv.DictReader(f, delimiter=";"))
    gewinne = [float(t["gewinn"]) for t in trades if t["art"] == "VERKAUF"]
    print(f"\n Abgeschlossene Trades: {len(gewinne)}")
    if gewinne:
        print(f" Mit Gewinn: {sum(g > 0 for g in gewinne)} | Summe: {sum(gewinne):+,.2f} EUR")
    print("\n Letzte 10 Aktionen:")
    for t in trades[-10:]:
        print(f"  {t['zeit']}  {t['art']:<7} {t['stueck']:>4} x {t['ticker']:<8} "
              f"{float(t['kurs']):>8.2f}  {t['gewinn']:>8}  {t['grund']}")


if __name__ == "__main__":
    main()
