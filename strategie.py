"""Die Handelsregeln: wann kaufen, wann verkaufen. Jeder Motor hat seine eigenen Zahlen (config.MOTOREN)."""

import os
from dataclasses import dataclass

import config


@dataclass(frozen=True)
class Motor:
    name: str
    titel: str
    beschreibung: str
    intervall: str
    zeitraum_live: str
    zeitraum_backtest: str
    pruef_abstand: int
    ema_kurz: int
    ema_lang: int
    trend_ema: int | None
    rsi_min_kauf: float
    rsi_max_kauf: float
    stop_loss: float
    take_profit: float
    trailing_stop: float
    verkauf_bei_trendwende: bool
    verkauf_unter_trend: bool
    nichts_ueber_nacht: bool
    sperre_stunden: float
    max_kaeufe_pro_tag: int

    @property
    def aufwaermen(self) -> int:
        """So viele Kerzen braucht der Motor, bevor seine Durchschnitte aussagekräftig sind."""
        return max(self.ema_lang, self.trend_ema or 0)

    @property
    def kerzen_minuten(self) -> int:
        zahl, einheit = int(self.intervall[:-1]), self.intervall[-1]
        return zahl * {"m": 1, "h": 60, "d": 1440}[einheit]


def motor_laden(name: str) -> Motor:
    return Motor(name=name, **config.MOTOREN[name])


def aktiver_motor() -> Motor:
    """Der auf der Webseite gewählte Motor, sonst der Standard aus config.py."""
    name = config.STANDARD_MOTOR
    if os.path.exists(config.MOTOR_DATEI):
        with open(config.MOTOR_DATEI, encoding="utf-8") as f:
            gewaehlt = f.read().strip()
        if gewaehlt in config.MOTOREN:
            name = gewaehlt
    return motor_laden(name)


def motor_waehlen(name: str):
    with open(config.MOTOR_DATEI, "w", encoding="utf-8") as f:
        f.write(name)


def indikatoren_berechnen(kerzen: list[dict], motor: Motor) -> list[dict]:
    """Fügt jeder Kerze Durchschnitte (EMA) und RSI hinzu."""
    a_kurz = 2 / (motor.ema_kurz + 1)
    a_lang = 2 / (motor.ema_lang + 1)
    a_trend = 2 / (motor.trend_ema + 1) if motor.trend_ema else None
    a_rsi = 1 / config.RSI_PERIODE
    ema_kurz = ema_lang = ema_trend = None
    avg_gewinn = avg_verlust = 0.0
    vorher = None

    for k in kerzen:
        c = k["close"]
        ema_kurz = c if ema_kurz is None else a_kurz * c + (1 - a_kurz) * ema_kurz
        ema_lang = c if ema_lang is None else a_lang * c + (1 - a_lang) * ema_lang
        if a_trend:
            ema_trend = c if ema_trend is None else a_trend * c + (1 - a_trend) * ema_trend
        if vorher is not None:
            diff = c - vorher
            avg_gewinn = a_rsi * max(diff, 0) + (1 - a_rsi) * avg_gewinn
            avg_verlust = a_rsi * max(-diff, 0) + (1 - a_rsi) * avg_verlust
        k["ema_kurz"] = ema_kurz
        k["ema_lang"] = ema_lang
        k["ema_trend"] = ema_trend
        k["rsi"] = 100.0 if avg_verlust == 0 else 100 - 100 / (1 + avg_gewinn / avg_verlust)
        vorher = c
    return kerzen


def kauf_signal(letzte: dict, vorletzte: dict, motor: Motor) -> str | None:
    """Kaufen, wenn der schnelle Durchschnitt den langsamen nach oben kreuzt (plus Filter des Motors)."""
    kreuzt_hoch = (vorletzte["ema_kurz"] <= vorletzte["ema_lang"]
                   and letzte["ema_kurz"] > letzte["ema_lang"])
    if not kreuzt_hoch:
        return None
    if not motor.rsi_min_kauf <= letzte["rsi"] < motor.rsi_max_kauf:
        return None
    if motor.trend_ema and not (letzte["close"] > letzte["ema_trend"]
                                and letzte["ema_lang"] > letzte["ema_trend"]):
        return None
    return f"Aufwärtstrend (EMA-Kreuz, RSI {letzte['rsi']:.0f})"


def verkauf_grund(kurs: float, letzte: dict, vorletzte: dict, position: dict,
                  motor: Motor) -> str | None:
    """Gibt einen Grund zurück, falls die Position verkauft werden soll."""
    einstand = position["einstandskurs"]
    hoch = max(position["hoechstkurs"], kurs)
    ergebnis = f"{kurs / einstand - 1:+.2%}"

    if kurs <= einstand * (1 - motor.stop_loss):
        return f"Stop-Loss ({ergebnis})"
    if kurs >= einstand * (1 + motor.take_profit):
        return f"Gewinnmitnahme ({ergebnis})"
    if hoch > einstand and kurs <= hoch * (1 - motor.trailing_stop):
        return f"Trailing-Stop ({ergebnis})"
    if (motor.verkauf_bei_trendwende
            and vorletzte["ema_kurz"] >= vorletzte["ema_lang"]
            and letzte["ema_kurz"] < letzte["ema_lang"]):
        return f"Trend dreht nach unten ({ergebnis})"
    if motor.verkauf_unter_trend and motor.trend_ema and letzte["close"] < letzte["ema_trend"]:
        return f"Langer Trend gebrochen ({ergebnis})"
    return None
