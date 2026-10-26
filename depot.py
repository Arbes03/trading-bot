"""Das Spielgeld-Depot: Bargeld, Positionen und Trade-Protokoll."""

import csv
import json
import math
import os
from datetime import datetime, timedelta

import config


class Depot:
    def __init__(self, datei: str | None = None, trades_datei: str | None = None):
        # Ohne Datei (z. B. im Backtest) wird nichts gespeichert.
        self.datei = datei
        self.trades_datei = trades_datei
        self.bargeld = config.STARTKAPITAL
        self.positionen: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.letzte_verkaeufe: dict[str, str] = {}      # ticker -> Zeitpunkt des letzten Verkaufs
        self.kaeufe_heute = {"tag": "", "anzahl": 0}
        if datei and os.path.exists(datei):
            with open(datei, encoding="utf-8") as f:
                daten = json.load(f)
            self.bargeld = daten["bargeld"]
            self.positionen = daten["positionen"]
            self.letzte_verkaeufe = daten.get("letzte_verkaeufe", {})
            self.kaeufe_heute = daten.get("kaeufe_heute", self.kaeufe_heute)

    def darf_kaufen(self, ticker: str, zeit: datetime, motor) -> bool:
        """Bremsen des Motors: Sperre nach Verkauf und Höchstzahl Käufe pro Tag."""
        if self.kaeufe_heute["tag"] == str(zeit.date()) and \
                self.kaeufe_heute["anzahl"] >= motor.max_kaeufe_pro_tag:
            return False
        verkauft = self.letzte_verkaeufe.get(ticker)
        if motor.sperre_stunden and verkauft:
            if zeit - datetime.fromisoformat(verkauft) < timedelta(hours=motor.sperre_stunden):
                return False
        return True

    def gesamtwert(self, kurse: dict[str, float]) -> float:
        wert = self.bargeld
        for ticker, pos in self.positionen.items():
            wert += pos["stueck"] * kurse.get(ticker, pos["einstandskurs"])
        return wert

    def kaufen(self, ticker: str, kurs: float, zeit, grund: str, depotwert: float, motor=None) -> bool:
        max_positionen = motor.positionen_hoechstens if motor else config.MAX_POSITIONEN
        anteil = motor.anteil_pro_position if motor else config.MAX_ANTEIL_PRO_POSITION
        if ticker in self.positionen or len(self.positionen) >= max_positionen:
            return False
        kaufkurs = kurs * (1 + config.SPREAD / 2)
        budget = min(depotwert * anteil,
                     self.bargeld - config.GEBUEHR_PRO_ORDER)
        stueck = math.floor(budget / kaufkurs)
        if stueck < 1:
            return False

        kosten = stueck * kaufkurs + config.GEBUEHR_PRO_ORDER
        self.bargeld -= kosten
        self.positionen[ticker] = {
            "stueck": stueck,
            "einstandskurs": kaufkurs,
            "hoechstkurs": kaufkurs,
            "kaufzeit": str(zeit),
            "kosten": kosten,
        }
        tag = str(zeit)[:10]
        if self.kaeufe_heute["tag"] != tag:
            self.kaeufe_heute = {"tag": tag, "anzahl": 0}
        self.kaeufe_heute["anzahl"] += 1
        self._protokollieren(zeit, "KAUF", ticker, stueck, kaufkurs, grund, None)
        return True

    def verkaufen(self, ticker: str, kurs: float, zeit, grund: str) -> float:
        pos = self.positionen.pop(ticker)
        verkaufskurs = kurs * (1 - config.SPREAD / 2)
        erloes = pos["stueck"] * verkaufskurs - config.GEBUEHR_PRO_ORDER
        self.bargeld += erloes
        gewinn = erloes - pos["kosten"]
        self.letzte_verkaeufe[ticker] = str(zeit)
        self._protokollieren(zeit, "VERKAUF", ticker, pos["stueck"], verkaufskurs, grund, gewinn)
        return gewinn

    def hoechstkurs_aktualisieren(self, ticker: str, kurs: float):
        pos = self.positionen[ticker]
        pos["hoechstkurs"] = max(pos["hoechstkurs"], kurs)

    def zuruecksetzen(self):
        """Alles auf Anfang: Startkapital, keine Positionen, Protokolle gelöscht."""
        self.bargeld = config.STARTKAPITAL
        self.positionen = {}
        self.trades = []
        self.letzte_verkaeufe = {}
        self.kaeufe_heute = {"tag": "", "anzahl": 0}
        for datei in (self.trades_datei, config.VERLAUF_DATEI):
            if datei and os.path.exists(datei):
                os.remove(datei)
        self.speichern()

    def speichern(self):
        if not self.datei:
            return
        with open(self.datei, "w", encoding="utf-8") as f:
            json.dump({"bargeld": self.bargeld, "positionen": self.positionen,
                       "letzte_verkaeufe": self.letzte_verkaeufe, "kaeufe_heute": self.kaeufe_heute},
                      f, indent=2, ensure_ascii=False)

    def _protokollieren(self, zeit, art, ticker, stueck, kurs, grund, gewinn):
        eintrag = {
            "zeit": str(zeit)[:19],
            "art": art,
            "ticker": ticker,
            "stueck": stueck,
            "kurs": round(kurs, 2),
            "gewinn": "" if gewinn is None else round(gewinn, 2),
            "grund": grund,
        }
        self.trades.append(eintrag)
        if self.trades_datei:
            neu = not os.path.exists(self.trades_datei)
            with open(self.trades_datei, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=eintrag.keys(), delimiter=";")
                if neu:
                    writer.writeheader()
                writer.writerow(eintrag)


def verlauf_eintragen(datei: str, zeit, wert: float):
    """Merkt sich den Depotwert für die Verlaufskurve."""
    neu = not os.path.exists(datei)
    with open(datei, "a", newline="", encoding="utf-8") as f:
        if neu:
            f.write("zeit;wert\n")
        f.write(f"{str(zeit)[:19]};{wert:.2f}\n")


def trades_lesen(datei: str) -> list[dict]:
    if not os.path.exists(datei):
        return []
    with open(datei, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def verlauf_lesen(datei: str) -> list[dict]:
    if not os.path.exists(datei):
        return []
    with open(datei, encoding="utf-8") as f:
        return [{"zeit": z["zeit"], "wert": float(z["wert"])}
                for z in csv.DictReader(f, delimiter=";")]
