"""Nachrichten aufs Handy über ntfy (kostenlos, ohne Konto: App "ntfy" installieren und Kanal abonnieren).

Der Kanalname steht NICHT im Code (das Projekt ist öffentlich), sondern in der Umgebungsvariable NTFY_THEMA.
Bei GitHub ist er als Geheimnis (Secret) hinterlegt. Ohne Kanalname werden keine Nachrichten verschickt.
"""

import json
import os
import urllib.request

import config


def eur(betrag: float, vorzeichen: bool = False) -> str:
    """1958.49 -> '1.958,49 €' (deutsche Schreibweise)."""
    text = f"{abs(betrag) if vorzeichen else betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    if vorzeichen:
        text = ("+" if betrag > 0 else "−" if betrag < 0 else "±") + text
    return f"{text} €"


def senden(titel: str, text: str, tags: list[str] | None = None, prioritaet: int = 3) -> bool:
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
        print(f"Nachricht konnte nicht gesendet werden: {fehler}")
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
