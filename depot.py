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
        self.bargeld = config.STARTKAPITAL  # Handelsgeld: damit kauft der Bot
        self.gewinnkonto = 0.0              # gesicherte Gewinne: werden NIE wieder investiert
        self.positionen: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.letzte_verkaeufe: dict[str, str] = {}      # ticker -> Zeitpunkt des letzten Verkaufs
        self.kaeufe_heute = {"tag": "", "anzahl": 0}
        self.pausiert: dict | None = None  # Notbremse/Wunsch: {"seit": ..., "grund": ..., "art": ...}
        self.verkauf_angefordert: str | None = None  # "alles verkaufen" gewünscht, wird bei offener Börse ausgeführt
        self.vergleich_start: dict | None = None  # Kurs des Vergleichs-ETF beim Start ("einfach halten")
        if datei and os.path.exists(datei):
            with open(datei, encoding="utf-8") as f:
                daten = json.load(f)
            self.bargeld = daten["bargeld"]
            self.gewinnkonto = daten.get("gewinnkonto", 0.0)
            self.positionen = daten["positionen"]
            self.letzte_verkaeufe = daten.get("letzte_verkaeufe", {})
            self.kaeufe_heute = daten.get("kaeufe_heute", self.kaeufe_heute)
            self.pausiert = daten.get("pausiert")
            self.verkauf_angefordert = daten.get("verkauf_angefordert")
            self.vergleich_start = daten.get("vergleich_start")

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

    def vergleichswert(self, kurse: dict[str, float], zeit) -> float | None:
        """Was wäre das Startkapital wert, wenn man es am Start einfach in den Vergleichs-ETF gesteckt hätte?"""
        kurs = kurse.get(config.VERGLEICH_ETF)
        if not kurs:
            return None
        if not self.vergleich_start:
            self.vergleich_start = {"kurs": kurs, "zeit": str(zeit)[:16]}
        return (config.STARTKAPITAL - config.GEBUEHR_PRO_ORDER) * kurs / self.vergleich_start["kurs"]

    def gesamtwert(self, kurse: dict[str, float]) -> float:
        """Alles zusammen: Handelsgeld, Aktien und gesicherte Gewinne."""
        return self.handelswert(kurse) + self.gewinnkonto

    def handelswert(self, kurse: dict[str, float]) -> float:
        """Nur das Geld, mit dem der Bot handelt (ohne das Gewinnkonto)."""
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
        # Der Anteil pro Aktie bezieht sich nur auf das Handelsgeld, das Gewinnkonto bleibt unangetastet
        budget = min((depotwert - self.gewinnkonto) * anteil,
                     self.bargeld - config.GEBUEHR_PRO_ORDER)
        if config.GRUPPE.get(ticker) == "Krypto" or config.BRUCHSTUECKE:
            stueck = math.floor(budget / kaufkurs * 1e6) / 1e6  # Bruchteile (z. B. 0,03 BTC oder 0,4 SAP-Aktien)
        else:
            stueck = math.floor(budget / kaufkurs)              # Aktien/ETFs: nur ganze Stücke
        if stueck <= 0:
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
        gewinn = erloes - pos["kosten"]
        if gewinn > 0 and config.GEWINNE_SICHERN:
            # Der Einsatz geht zurück ins Handelsgeld, der Gewinn wird beiseitegelegt
            self.bargeld += erloes - gewinn
            self.gewinnkonto += gewinn
        else:
            self.bargeld += erloes
        self.letzte_verkaeufe[ticker] = str(zeit)
        self._protokollieren(zeit, "VERKAUF", ticker, pos["stueck"], verkaufskurs, grund, gewinn)
        return gewinn

    def hoechstkurs_aktualisieren(self, ticker: str, kurs: float):
        pos = self.positionen[ticker]
        pos["hoechstkurs"] = max(pos["hoechstkurs"], kurs)

    def zuruecksetzen(self):
        """Alles auf Anfang: Startkapital, keine Positionen, Protokolle gelöscht."""
        self.bargeld = config.STARTKAPITAL
        self.gewinnkonto = 0.0
        self.positionen = {}
        self.trades = []
        self.letzte_verkaeufe = {}
        self.kaeufe_heute = {"tag": "", "anzahl": 0}
        self.pausiert = None
        self.verkauf_angefordert = None
        self.vergleich_start = None
        for datei in (self.trades_datei, config.VERLAUF_DATEI):
            if datei and os.path.exists(datei):
                os.remove(datei)
        self.speichern()

    def speichern(self):
        if not self.datei:
            return
        with open(self.datei, "w", encoding="utf-8") as f:
            json.dump({"bargeld": self.bargeld, "gewinnkonto": self.gewinnkonto, "positionen": self.positionen,
                       "letzte_verkaeufe": self.letzte_verkaeufe, "kaeufe_heute": self.kaeufe_heute,
                       "pausiert": self.pausiert, "verkauf_angefordert": self.verkauf_angefordert,
                       "vergleich_start": self.vergleich_start},
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


def verlauf_eintragen(datei: str, zeit, wert: float, halten: float | None = None):
    """Merkt sich den Depotwert (und den Vergleichswert "ETF halten") für die Verlaufskurve."""
    if os.path.exists(datei):
        with open(datei, encoding="utf-8") as f:
            inhalt = f.read().splitlines()
        if inhalt and "halten" not in inhalt[0]:  # ältere Datei ohne Vergleichsspalte erweitern
            with open(datei, "w", newline="", encoding="utf-8") as f:
                f.write("zeit;wert;halten\n" + "".join(f"{z};\n" for z in inhalt[1:]))
    neu = not os.path.exists(datei)
    with open(datei, "a", newline="", encoding="utf-8") as f:
        if neu:
            f.write("zeit;wert;halten\n")
        f.write(f"{str(zeit)[:19]};{wert:.2f};{'' if halten is None else f'{halten:.2f}'}\n")


def trades_lesen(datei: str) -> list[dict]:
    if not os.path.exists(datei):
        return []
    with open(datei, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def verlauf_lesen(datei: str) -> list[dict]:
    if not os.path.exists(datei):
        return []
    with open(datei, encoding="utf-8") as f:
        return [{"zeit": z["zeit"], "wert": float(z["wert"]),
                 "halten": float(z["halten"]) if z.get("halten") else None}
                for z in csv.DictReader(f, delimiter=";")]
