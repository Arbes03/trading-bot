"""Testet einen Strategie-Motor an vergangenen Kursen, als hätte der Bot damals schon gehandelt.

Normalerweise über die Webseite gestartet (webseite.py).
Ohne Webseite:  python backtest.py      (vergleicht beide Motoren)
"""

from datetime import datetime

import config
from daten import fuer_alle, kurse_laden
from depot import Depot
from handel import kaeufe_erlaubt, notbremse_pruefen, ticker_pruefen
from strategie import Motor, motor_laden, reihenfolge

KURVEN_PUNKTE = 600  # so viele Punkte bekommt die Kurve höchstens


def daten_laden(motor: Motor) -> dict[str, list[dict]]:
    geladen, _ = fuer_alle(lambda t: kurse_laden(t, motor.zeitraum_backtest, motor), config.WATCHLIST)
    # Reihenfolge wie in der Watchlist, damit der Test bei jedem Lauf gleich abläuft
    return {t: geladen[t] for t in config.WATCHLIST if len(geladen.get(t, [])) > motor.aufwaermen}


def backtest_ausfuehren(motor: Motor, ab: datetime | None = None, daten: dict | None = None) -> dict:
    """Spielt den Motor durch. Mit `ab` wird erst ab diesem Zeitpunkt gehandelt (für faire Vergleiche)."""
    daten = daten if daten is not None else daten_laden(motor)
    if not daten:
        raise RuntimeError("Keine Kursdaten geladen. Internetverbindung prüfen.")

    # Für jede Aktie: Zeitpunkt -> Position in der Kerzenliste
    positionen = {t: {k["zeit"]: i for i, k in enumerate(kerzen)} for t, kerzen in daten.items()}
    zeitachse = sorted(set().union(*positionen.values()))

    depot = Depot()
    kurse: dict[str, float] = {}
    startkurse: dict[str, float] = {}
    tag, tagesstart = None, config.STARTKAPITAL
    hoechster_wert, max_rueckgang, tiefster_wert = config.STARTKAPITAL, 0.0, config.STARTKAPITAL
    kurve = []

    for zeit in zeitachse:
        if ab and zeit < ab:
            continue
        if zeit.date() != tag:
            tag = zeit.date()
            tagesstart = depot.gesamtwert(kurse)

        jetzt_da = {}
        for ticker, kerzen in daten.items():
            i = positionen[ticker].get(zeit)
            if i is not None and i >= motor.aufwaermen:
                jetzt_da[ticker] = i
        for ticker, i in jetzt_da.items():
            kurse[ticker] = daten[ticker][i]["close"]
            startkurse.setdefault(ticker, kurse[ticker])

        # Notbremse aktiv: nur noch Kurse mitschreiben (für die Vergleichskurve), nicht mehr handeln
        if not depot.pausiert:
            for ticker in reihenfolge({t: daten[t][i] for t, i in jetzt_da.items()}, depot.positionen, motor):
                kerzen, i = daten[ticker], jetzt_da[ticker]
                depotwert = depot.gesamtwert(kurse)
                ticker_pruefen(depot, motor, ticker, kerzen[i], kerzen[i - 1], kurse[ticker], zeit,
                               kaeufe_erlaubt(zeit, depotwert, tagesstart, motor), depotwert)
            notbremse_pruefen(depot, kurse, zeit)

        if not startkurse:
            continue
        wert = depot.gesamtwert(kurse)
        hoechster_wert = max(hoechster_wert, wert)
        max_rueckgang = max(max_rueckgang, 1 - wert / hoechster_wert)
        tiefster_wert = min(tiefster_wert, wert)
        # Vergleich: am Anfang alles gleichmäßig kaufen und liegen lassen
        halten = config.STARTKAPITAL * sum(kurse[t] / s for t, s in startkurse.items()) / len(startkurse)
        kurve.append({"zeit": zeit.strftime("%Y-%m-%d %H:%M"), "bot": round(wert, 2), "halten": round(halten, 2)})

    if not kurve:
        raise RuntimeError("Zu wenig Kursdaten für diesen Motor.")
    for ticker in list(depot.positionen):
        depot.verkaufen(ticker, kurse[ticker], zeitachse[-1], "Ende des Tests")

    verkaeufe = [t for t in depot.trades if t["art"] == "VERKAUF"]
    gewinne = [t["gewinn"] for t in verkaeufe if t["gewinn"] > 0]
    verluste = [t["gewinn"] for t in verkaeufe if t["gewinn"] <= 0]
    handelstage = len({k["zeit"][:10] for k in kurve})
    schritt = max(1, len(kurve) // KURVEN_PUNKTE)
    return {
        "motor": motor.name,
        "motor_titel": motor.titel,
        "von": f"{datetime.fromisoformat(kurve[0]['zeit']):%d.%m.%Y}",
        "bis": f"{datetime.fromisoformat(kurve[-1]['zeit']):%d.%m.%Y}",
        "handelstage": handelstage,
        "startkapital": config.STARTKAPITAL,
        "endwert": depot.bargeld,
        "halten_endwert": kurve[-1]["halten"],
        "trades": len(verkaeufe),
        "gewinn_trades": len(gewinne),
        "avg_gewinn": sum(gewinne) / max(len(gewinne), 1),
        "avg_verlust": sum(verluste) / max(len(verluste), 1),
        "gebuehren": len(depot.trades) * config.GEBUEHR_PRO_ORDER,
        "tiefster_wert": tiefster_wert,
        "max_rueckgang": max_rueckgang,
        "kurve": kurve[::schritt] + ([kurve[-1]] if (len(kurve) - 1) % schritt else []),
        "letzte_trades": depot.trades[-50:],
        "notbremse": depot.pausiert,  # None = nicht ausgelöst
    }


def zeile(titel: str, e: dict) -> str:
    start = e["startkapital"]
    bot, halten = e["endwert"] - start, e["halten_endwert"] - start
    quote = f"{e['gewinn_trades'] / e['trades']:.0%}" if e["trades"] else "-"
    return (f" {titel:<34} {e['von']}-{e['bis']}  {bot:>+10,.2f} ({bot / start:+6.1%})  "
            f"{halten:>+10,.2f} ({halten / start:+6.1%})  {e['trades']:>5}  {quote:>4}  "
            f"{e['gebuehren']:>8,.0f}  {e['max_rueckgang']:>6.1%}")


def main():
    print("Lade Kursdaten (5-Minuten für 60 Tage, Stundenkerzen für 2 Jahre) ...")
    e_schnell = backtest_ausfuehren(motor_laden("schnell"))
    ab = None
    zeilen = [("Schnell (letzte ~60 Tage)", e_schnell)]
    lang = []
    for name in ("vorsichtig", "offensiv"):
        motor = motor_laden(name)
        daten = daten_laden(motor)
        if ab is None:
            zone = daten[next(iter(daten))][0]["zeit"].tzinfo
            ab = datetime.strptime(e_schnell["kurve"][0]["zeit"], "%Y-%m-%d %H:%M").replace(tzinfo=zone)
        zeilen.append((f"{motor.titel} (gleiche ~60 Tage)", backtest_ausfuehren(motor, ab=ab, daten=daten)))
        lang.append((f"{motor.titel} (2 Jahre)", backtest_ausfuehren(motor, daten=daten)))

    print()
    print("=" * 128)
    print(f" {'Motor':<34} {'Zeitraum':<21}  {'Ergebnis Bot':>21}  {'Kaufen & halten':>21}  "
          f"{'Trades':>5}  {'Quote':>4}  {'Gebühren':>8}  {'Rückgang':>6}")
    print("-" * 128)
    for titel, e in zeilen + lang:
        print(zeile(titel, e))
    print("=" * 128)
    for titel, e in zeilen + lang:
        if e["notbremse"]:
            print(f" Notbremse bei \"{titel}\" ausgelöst am {e['notbremse']['seit']}: {e['notbremse']['grund']}")
    print(" Quote = Anteil der Trades mit Gewinn. Rückgang = größter Verlust vom Höchststand.")
    print(" Steuern (ca. 26 % auf Gewinne) sind nicht eingerechnet. Vergangenheit garantiert nichts.")


if __name__ == "__main__":
    main()
