"""Nachrichten aufs Handy: per Telegram, WhatsApp (CallMeBot) und/oder App "ntfy". Alles kostenlos.

Die Zugangsdaten stehen NICHT im Code (das Projekt ist öffentlich), sondern in Umgebungsvariablen,
die bei GitHub als Geheimnisse (Secrets) hinterlegt sind:
  TELEGRAM_TOKEN        der Schlüssel deines Telegram-Bots (von @BotFather)
  TELEGRAM_CHAT_ID      deine Telegram-Nutzer-ID (von @userinfobot)
  CALLMEBOT_TELEFON     deine WhatsApp-Nummer mit Ländervorwahl, z. B. +491701234567
  CALLMEBOT_SCHLUESSEL  der API-Schlüssel, den CallMeBot dir per WhatsApp geschickt hat
  NTFY_THEMA            (optional) Kanalname für die App "ntfy"
Was nicht hinterlegt ist, wird einfach nicht benutzt.
"""

import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import config

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Letzte Fehlermeldung (ohne Zugangsdaten), wird zur Kontrolle in benachrichtigung.json gespeichert
letzter_fehler = ""


def _fehler(text: str):
    global letzter_fehler
    letzter_fehler = text
    print(text)


def eur(betrag: float, vorzeichen: bool = False) -> str:
    """1958.49 -> '1.958,49 €' (deutsche Schreibweise)."""
    text = f"{abs(betrag) if vorzeichen else betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    if vorzeichen:
        text = ("+" if betrag > 0 else "−" if betrag < 0 else "±") + text
    return f"{text} €"


def eingerichtet() -> str:
    """Welche Wege eingerichtet sind, z. B. 'WhatsApp' oder 'WhatsApp + ntfy' (leer = keiner)."""
    wege = []
    if os.environ.get("TELEGRAM_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip():
        wege.append("Telegram")
    if os.environ.get("CALLMEBOT_TELEFON", "").strip() and os.environ.get("CALLMEBOT_SCHLUESSEL", "").strip():
        wege.append("WhatsApp")
    if os.environ.get("NTFY_THEMA", "").strip():
        wege.append("ntfy")
    return " + ".join(wege)


def senden(titel: str, text: str, tags: list[str] | None = None, prioritaet: int = 3) -> bool:
    """Schickt die Nachricht über alle eingerichteten Wege. True, wenn mindestens einer geklappt hat."""
    telegram = telegram_senden(titel, text)
    whatsapp = whatsapp_senden(titel, text)
    ntfy = ntfy_senden(titel, text, tags, prioritaet)
    return telegram or whatsapp or ntfy


def telegram_senden(titel: str, text: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return False
    inhalt = f"<b>{html.escape(titel)}</b>\n{html.escape(text)}\n\n{config.WEBSEITE_URL}"
    daten = {"chat_id": chat_id, "text": inhalt, "parse_mode": "HTML", "disable_web_page_preview": True}
    anfrage = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps(daten).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return json.load(antwort).get("ok", False)
    except urllib.error.HTTPError as fehler:
        # Fehlertext von Telegram ausgeben, aber nie die Adresse (sie enthält den Schlüssel)
        beschreibung = json.loads(fehler.read() or b"{}").get("description", "")
        _fehler(f"Telegram-Nachricht abgelehnt ({fehler.code}): {beschreibung}. "
                "Tipp: Hast du deinem Bot schon einmal /start geschrieben? Stimmen Token und Chat-ID?")
    except Exception as fehler:
        _fehler(f"Telegram-Nachricht konnte nicht gesendet werden: {type(fehler).__name__}")
    return False


def whatsapp_senden(titel: str, text: str) -> bool:
    telefon = os.environ.get("CALLMEBOT_TELEFON", "").replace(" ", "").strip()
    schluessel = os.environ.get("CALLMEBOT_SCHLUESSEL", "").strip()
    if not (telefon and schluessel):
        return False
    inhalt = f"*{titel}*\n{text}\n{config.WEBSEITE_URL}"
    url = f"{CALLMEBOT_URL}?" + urllib.parse.urlencode({"phone": telefon, "text": inhalt, "apikey": schluessel})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "trading-bot"}),
                                    timeout=30) as antwort:
            ok = antwort.status == 200 and "error" not in antwort.read().decode("utf-8", "ignore").lower()
    except Exception as fehler:
        print(f"WhatsApp-Nachricht konnte nicht gesendet werden: {type(fehler).__name__}")
        return False
    if not ok:
        print("WhatsApp-Nachricht wurde von CallMeBot abgelehnt (Nummer oder Schlüssel prüfen).")
    return ok


def ntfy_senden(titel: str, text: str, tags: list[str] | None, prioritaet: int) -> bool:
    thema = os.environ.get("NTFY_THEMA", "").strip()
    if not thema:
        return False
    nachricht = {
        "topic": thema,
        "title": titel,
        "message": text,
        "tags": tags or [],
        "priority": prioritaet,
        "click": config.WEBSEITE_URL,
    }
    anfrage = urllib.request.Request(config.NTFY_SERVER, data=json.dumps(nachricht).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=15):
            return True
    except Exception as fehler:
        print(f"ntfy-Nachricht konnte nicht gesendet werden: {fehler}")
        return False


def trade_melden(trade: dict, depotwert: float):
    name = config.WATCHLIST.get(trade["ticker"], trade["ticker"])
    betrag = trade["stueck"] * trade["kurs"]
    if trade["art"] == "KAUF":
        senden(f"KAUF {name}",
               f"{trade['stueck']} Stück zu {eur(trade['kurs'])} = {eur(betrag)} investiert\n"
               f"Grund: {trade['grund']}\nDepot jetzt: {eur(depotwert)}",
               tags=["shopping_cart"])
    else:
        gewinn = trade["gewinn"]
        senden(f"VERKAUF {name}: {eur(gewinn, vorzeichen=True)}",
               f"{trade['stueck']} Stück zu {eur(trade['kurs'])} = {eur(betrag)}\n"
               f"Grund: {trade['grund']}\nDepot jetzt: {eur(depotwert)}",
               tags=["chart_with_upwards_trend" if gewinn > 0 else "chart_with_downwards_trend"])


def willkommen_melden(status: dict, wege: str) -> bool:
    e = status["ergebnis"]
    investiert = sum(p["investiert"] for p in status["positionen"])
    return senden("Trading-Bot verbunden ✅",
                  f"Ab jetzt bekommst du hier Nachrichten ({wege}): bei jedem Kauf und Verkauf "
                  f"und jeden Handelstag nach Börsenschluss einen Tagesabschluss.\n\n"
                  f"Stand jetzt: Depot {eur(status['depotwert'])} ({eur(e['gesamt'], vorzeichen=True)} seit Start), "
                  f"investiert {eur(investiert)} in {len(status['positionen'])} Werten, Bargeld {eur(status['bargeld'])}.",
                  tags=["wave"])


def tagesabschluss_melden(status: dict, datum: str):
    e = status["ergebnis"]
    zeilen = [
        f"Depot: {eur(status['depotwert'])}",
        f"Heute: {eur(e['heute'], vorzeichen=True)} · seit Start: {eur(e['gesamt'], vorzeichen=True)}",
    ]
    if status["positionen"]:
        zeilen.append("Investiert:")
        for p in sorted(status["positionen"], key=lambda p: -p["wert"]):
            zeilen.append(f"• {p['name']}: {eur(p['investiert'])} → {eur(p['wert'])} ({eur(p['gewinn'], vorzeichen=True)})")
    else:
        zeilen.append("Gerade nichts investiert.")
    zeilen.append(f"Bargeld: {eur(status['bargeld'])}")
    heute = [t for t in status["trades"] if t["zeit"][:10] == datum]
    kaeufe = sum(t["art"] == "KAUF" for t in heute)
    verkaeufe = sum(t["art"] == "VERKAUF" for t in heute)
    zeilen.append(f"Heute: {kaeufe} Käufe, {verkaeufe} Verkäufe")
    lage = "im Plus" if e["gesamt"] > 0.005 else "im Minus" if e["gesamt"] < -0.005 else "ausgeglichen"
    senden(f"Tagesabschluss: {lage} ({eur(e['gesamt'], vorzeichen=True)})", "\n".join(zeilen),
           tags=["bar_chart"])
