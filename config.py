# Einstellungen für den Demo-Trading-Bot.
# Hier kannst du alles anpassen, ohne den restlichen Code anzufassen.

# --- Spielgeld ---
STARTKAPITAL = 10_000.00  # Euro

# --- Was beobachtet wird (Yahoo-Finance-Kürzel, ".DE" = Xetra) ---
# Neutrale Auswahl: alle DAX-Werte plus große Index-ETFs. Keine Empfehlung.
# Werte entfernen = Zeile löschen, hinzufügen = Zeile mit Kürzel von finance.yahoo.com.

# Die 40 DAX-Unternehmen (Stand Juni 2026: Hochtief neu, Porsche SE raus)
DAX_AKTIEN = {
    "ADS.DE": "Adidas",
    "AIR.DE": "Airbus",
    "ALV.DE": "Allianz",
    "BAS.DE": "BASF",
    "BAYN.DE": "Bayer",
    "BEI.DE": "Beiersdorf",
    "BMW.DE": "BMW",
    "BNR.DE": "Brenntag",
    "CBK.DE": "Commerzbank",
    "CON.DE": "Continental",
    "DTG.DE": "Daimler Truck",
    "DBK.DE": "Deutsche Bank",
    "DB1.DE": "Deutsche Börse",
    "DHL.DE": "DHL Group",
    "DTE.DE": "Deutsche Telekom",
    "EOAN.DE": "E.ON",
    "FRE.DE": "Fresenius",
    "FME.DE": "Fresenius Medical Care",
    "G1A.DE": "GEA Group",
    "HNR1.DE": "Hannover Rück",
    "HEI.DE": "Heidelberg Materials",
    "HEN3.DE": "Henkel",
    "HOT.DE": "Hochtief",
    "IFX.DE": "Infineon",
    "MBG.DE": "Mercedes-Benz",
    "MRK.DE": "Merck",
    "MTX.DE": "MTU Aero Engines",
    "MUV2.DE": "Münchener Rück",
    "QIA.DE": "Qiagen",
    "RHM.DE": "Rheinmetall",
    "RWE.DE": "RWE",
    "SAP.DE": "SAP",
    "G24.DE": "Scout24",
    "SIE.DE": "Siemens",
    "ENR.DE": "Siemens Energy",
    "SHL.DE": "Siemens Healthineers",
    "SY1.DE": "Symrise",
    "VOW3.DE": "Volkswagen",
    "VNA.DE": "Vonovia",
    "ZAL.DE": "Zalando",
}

# Große, breit gestreute Index-ETFs
ETFS = {
    "EUNL.DE": "iShares MSCI World",
    "VWCE.DE": "Vanguard FTSE All-World",
    "SXR8.DE": "iShares S&P 500",
    "SXRV.DE": "iShares Nasdaq 100",
    "EXS1.DE": "iShares DAX",
    "SXRT.DE": "iShares Euro Stoxx 50",
    "EXSA.DE": "iShares Stoxx Europe 600",
    "IS3N.DE": "iShares MSCI Schwellenländer",
}

WATCHLIST = {**DAX_AKTIEN, **ETFS}
GRUPPE = {**{t: "Aktie" for t in DAX_AKTIEN}, **{t: "ETF" for t in ETFS}}

# --- Kosten (realistisch simuliert) ---
GEBUEHR_PRO_ORDER = 1.00  # Euro pro Kauf bzw. Verkauf
SPREAD = 0.0005           # 0,05 % Unterschied zwischen Kauf- und Verkaufskurs

# --- Risiko ---
MAX_ANTEIL_PRO_POSITION = 0.20  # höchstens 20 % des Depotwerts pro Aktie
MAX_POSITIONEN = 5
TAGES_VERLUST_LIMIT = 0.03      # ab -3 % an einem Tag: keine neuen Käufe mehr

# --- Strategie-Motoren ---
# Der Bot handelt mit einem Motor. Umschalten geht auf der Webseite (Strategie & Einstellungen).
STANDARD_MOTOR = "vorsichtig"

MOTOREN = {
    "vorsichtig": dict(
        titel="Vorsichtig",
        beschreibung="Stundenkerzen, kauft nur in längeren Aufwärtstrends, hält auch über Nacht, wenige Trades.",
        intervall="1h",              # Kerzen-Größe
        zeitraum_live="60d",         # so viel Vergangenheit lädt der Bot für seine Berechnungen
        zeitraum_backtest="2y",      # Yahoo liefert Stundenkerzen für bis zu 2 Jahre
        pruef_abstand=900,           # alle 15 Minuten nachschauen
        ema_kurz=20,                 # schneller Durchschnitt (in Kerzen)
        ema_lang=50,                 # langsamer Durchschnitt
        trend_ema=200,               # langer Trend (ca. 1 Monat): nur darüber kaufen
        rsi_min_kauf=50,             # nur kaufen, wenn Schwung nach oben da ist ...
        rsi_max_kauf=70,             # ... aber nicht schon überkauft
        stop_loss=0.04,              # verkaufen bei -4 %
        take_profit=0.10,            # Gewinn mitnehmen bei +10 %
        trailing_stop=0.05,          # verkaufen, wenn Kurs 5 % unter das Hoch seit Kauf fällt
        verkauf_bei_trendwende=False,
        verkauf_unter_trend=True,    # verkaufen, wenn der lange Trend bricht
        nichts_ueber_nacht=False,
        sperre_stunden=24,           # nach Verkauf diese Aktie 24 h nicht wieder kaufen
        max_kaeufe_pro_tag=2,
    ),
    "offensiv": dict(
        titel="Offensiv (Momentum)",
        beschreibung="Stundenkerzen, kauft die Aktien, die in den letzten Tagen am stärksten gestiegen sind, "
                     "setzt größere Beträge, sichert Gewinne schneller.",
        intervall="1h",
        zeitraum_live="60d",
        zeitraum_backtest="2y",
        pruef_abstand=900,
        ema_kurz=20,
        ema_lang=50,
        trend_ema=200,
        rsi_min_kauf=0,
        rsi_max_kauf=75,
        stop_loss=0.03,              # schneller raus bei Verlust
        take_profit=0.08,
        trailing_stop=0.04,
        verkauf_bei_trendwende=True,
        verkauf_unter_trend=True,
        nichts_ueber_nacht=False,
        sperre_stunden=24,
        max_kaeufe_pro_tag=3,
        einstieg="momentum",         # nicht auf ein Kreuz warten, sondern die stärksten Werte kaufen
        momentum_kerzen=45,          # Anstieg der letzten ca. 5 Handelstage
        momentum_min=0.03,           # mindestens +3 % in diesen 5 Tagen
        max_anteil=0.33,             # bis zu 33 % des Depots pro Aktie
        max_positionen=3,
    ),
    "schnell": dict(
        titel="Schnell (Daytrading)",
        beschreibung="5-Minuten-Kerzen, reagiert auf jede kleine Bewegung, verkauft abends alles, sehr viele Trades.",
        intervall="5m",
        zeitraum_live="5d",
        zeitraum_backtest="60d",     # Yahoo liefert 5-Minuten-Kerzen nur für 60 Tage
        pruef_abstand=300,
        ema_kurz=9,
        ema_lang=21,
        trend_ema=None,
        rsi_min_kauf=0,
        rsi_max_kauf=70,
        stop_loss=0.02,
        take_profit=0.04,
        trailing_stop=0.015,
        verkauf_bei_trendwende=True,
        verkauf_unter_trend=False,
        nichts_ueber_nacht=True,
        sperre_stunden=0,
        max_kaeufe_pro_tag=999,
    ),
}
RSI_PERIODE = 14

# --- Handelszeiten Xetra (deutsche Zeit) ---
ZEITZONE = "Europe/Berlin"
BOERSE_AUF = "09:00"
BOERSE_ZU = "17:30"
ALLES_VERKAUFEN_AB = "17:20"  # nur Daytrading-Motor: nichts über Nacht halten
KEINE_KAEUFE_VOR = "09:30"    # erste halbe Stunde ist oft sehr wild

# --- Dateien ---
DEPOT_DATEI = "depot.json"
TRADES_DATEI = "trades.csv"
VERLAUF_DATEI = "verlauf.csv"
MOTOR_DATEI = "motor.txt"  # merkt sich den auf der Webseite gewählten Motor

# --- Webseite ---
WEB_PORT = 8050
WEBSEITE_URL = "https://arbes03.github.io/trading-bot/"

# --- Handy-Nachrichten (App "ntfy") ---
NTFY_SERVER = "https://ntfy.sh"
NACHRICHT_BEI_TRADES = True        # bei jedem Kauf und Verkauf
NACHRICHT_TAGESABSCHLUSS = True    # einmal pro Handelstag nach Börsenschluss
BENACHRICHTIGUNG_DATEI = "benachrichtigung.json"  # merkt sich, wann der letzte Tagesabschluss kam
