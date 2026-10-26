"""Der Live-Bot: beobachtet die Kurse und handelt mit Spielgeld.

Normalerweise über die Webseite gestartet (webseite.py).
Ohne Webseite:  python bot.py      (beenden mit Strg+C)
"""

import threading
from contextlib import nullcontext
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
from daten import fuer_alle, kurse_laden
from depot import Depot, verlauf_eintragen
from handel import kaeufe_erlaubt, notbremse_pruefen, ticker_pruefen, uhrzeit
from strategie import Motor, aktiver_motor, reihenfolge

ZONE = ZoneInfo(config.ZEITZONE)


def boerse_offen(jetzt: datetime) -> bool:
    return jetzt.weekday() < 5 and config.BOERSE_AUF <= uhrzeit(jetzt) < config.BOERSE_ZU


def runde(depot: Depot, motor: Motor, tagesstart: float, sperre=None) -> tuple[dict, list[str], int]:
    """Eine Prüfrunde: Kurse laden, handeln, speichern.

    Gibt (aktuelle Kurse, Meldungen, Anzahl Werte mit aktuellen Daten) zurück.
    """
    jetzt = datetime.now(ZONE)
    geladen, fehler = fuer_alle(lambda t: kurse_laden(t, motor.zeitraum_live, motor), config.WATCHLIST)
    meldungen = [f"Fehler beim Laden von {t}: {f}" for t, f in fehler.items()]
    # Feiertag oder Datenproblem: keine aktuellen Kurse, also nicht handeln
    max_alter = timedelta(minutes=motor.kerzen_minuten + 30)
    daten = {t: k for t, k in geladen.items()
             if len(k) >= motor.aufwaermen + 2 and jetzt - k[-1]["zeit"] <= max_alter}

    # Laden dauert, gehandelt wird erst danach unter der Sperre
    with sperre or nullcontext():
        kurse = {t: p["einstandskurs"] for t, p in depot.positionen.items()}
        kurse.update({t: k[-1]["close"] for t, k in daten.items()})
        darf_kaufen = kaeufe_erlaubt(jetzt, depot.gesamtwert(kurse), tagesstart, motor)

        notbremse = notbremse_pruefen(depot, kurse, jetzt)
        if notbremse:
            meldungen.append(notbremse)
        # Notbremse aktiv: nichts mehr handeln, bis du sie aufhebst
        for ticker in [] if depot.pausiert else reihenfolge({t: k[-2] for t, k in daten.items()}, depot.positionen, motor):
            kerzen = daten[ticker]
            # Die letzte Kerze läuft noch, Signale daher auf den abgeschlossenen Kerzen
            meldung = ticker_pruefen(depot, motor, ticker, kerzen[-2], kerzen[-3], kurse[ticker],
                                     jetzt, darf_kaufen, depot.gesamtwert(kurse))
            if meldung:
                meldungen.append(meldung)

        depot.speichern()
        verlauf_eintragen(config.VERLAUF_DATEI, jetzt, depot.gesamtwert(kurse))
    return kurse, meldungen, len(daten)


class Bot:
    """Die Dauerschleife. Läuft im Hintergrund, bis `stoppen()` aufgerufen wird."""

    def __init__(self, depot: Depot, melden=print, sperre=None):
        self.depot = depot
        self.melden = melden
        self.sperre = sperre
        self.kurse: dict[str, float] = {}
        self.letzte_runde: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def laeuft(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def starten(self):
        if self.laeuft:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.schleife, daemon=True)
        self._thread.start()

    def stoppen(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)
        self.melden("Bot gestoppt.")

    def schleife(self):
        self.melden("Bot gestartet.")
        tag, tagesstart, geschlossen_gemeldet = None, self.depot.bargeld, False
        while not self._stop.is_set():
            jetzt = datetime.now(ZONE)
            if not boerse_offen(jetzt):
                if not geschlossen_gemeldet:
                    self.melden(f"Börse geschlossen, warte auf Öffnung "
                                f"(Mo-Fr {config.BOERSE_AUF}-{config.BOERSE_ZU}) ...")
                    geschlossen_gemeldet = True
                self._stop.wait(60)
                continue

            if geschlossen_gemeldet:
                self.melden("Börse offen, Bot beobachtet die Kurse.")
                geschlossen_gemeldet = False
            if jetzt.date() != tag:
                tag = jetzt.date()
                tagesstart = self.depot.gesamtwert({})
            motor = aktiver_motor()  # jede Runde neu, damit ein Wechsel auf der Webseite sofort greift
            try:
                self.kurse, meldungen, anzahl = runde(self.depot, motor, tagesstart, self.sperre)
            except Exception as fehler:
                self.melden(f"Fehler in der Prüfrunde: {fehler}")
                self._stop.wait(60)
                continue
            self.letzte_runde = jetzt
            for m in meldungen:
                self.melden(m)
            wert = self.depot.gesamtwert(self.kurse)
            self.melden(f"Prüfrunde fertig ({motor.titel}): Depot {wert:,.2f} EUR, "
                        f"Kurse für {anzahl}/{len(config.WATCHLIST)} Werte")
            self._stop.wait(motor.pruef_abstand)


def main():
    depot = Depot(config.DEPOT_DATEI, config.TRADES_DATEI)
    print("DEMO-TRADING-BOT (nur Spielgeld). Beenden mit Strg+C.")
    bot = Bot(depot, lambda text: print(f"[{datetime.now(ZONE):%d.%m. %H:%M}] {text}"))
    try:
        bot.schleife()
    except KeyboardInterrupt:
        depot.speichern()
        print("\nBot gestoppt, Depot gespeichert.")


if __name__ == "__main__":
    main()
