"""„Wie läuft's?“: der Bot erklärt in ein paar Sätzen die Lage und spricht sie mit einer echten Stimme.

Der Text entsteht aus den aktuellen Daten (status_bauen). Die Sprachdatei erzeugt eine
Microsoft-Neural-Stimme über das Paket edge-tts. Klappt das nicht (kein Internet, Paket fehlt),
liest die Webseite den Text mit der Stimme des Geräts vor. Der Bot läuft in jedem Fall weiter.
"""

import asyncio
import os
from datetime import datetime

import config

ZEITLIMIT = 90  # Sekunden für die Sprachdatei, danach ohne Stimme weiter


def _ganz(x: float) -> str:
    return f"{round(x):,}".replace(",", ".")


def euro(x: float) -> str:
    """Gut vorlesbar: "11 Euro 61" statt "11,61 €"."""
    cent = round(abs(x) * 100)
    ganze, rest = divmod(cent, 100)
    if ganze >= 100:
        return f"rund {_ganz(abs(x))} Euro"
    if ganze == 0:
        return f"{rest} Cent"
    return f"{ganze} Euro {rest}" if rest else f"{ganze} Euro"


def prozent(x: float) -> str:
    zahl = f"{abs(x) * 100:.1f}".replace(".", ",").removesuffix(",0")
    return f"{zahl} Prozent"


def plus_minus(x: float) -> str:
    return ("plus " if x >= 0 else "minus ") + prozent(x)


def kurs(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " Euro"


def saetze_bauen(s: dict, jetzt: datetime) -> list[str]:
    m, e, nb = s["einstellungen"]["motor"], s["ergebnis"], s.get("notbremse") or {}
    saetze = []
    gruss = "Guten Morgen" if jetzt.hour < 11 else "Hallo" if jetzt.hour < 18 else "Guten Abend"
    motor = m["titel"].split(" (")[0]
    saetze.append(f"{gruss}! Hier ist dein Trading-Bot, ich fahre gerade den Motor {motor}. "
                  f"Stand: {jetzt:%H:%M} Uhr.")

    # Wie steht das Depot?
    g = e["gesamt"]
    saetze.append(f"Dein Depot ist {euro(s['depotwert'])} wert. " + (
        "Das ist ungefähr so viel wie am Start." if abs(g) < 0.5 else
        f"Das sind {euro(g)} {'mehr' if g > 0 else 'weniger'} als die {_ganz(s['startkapital'])} Euro Startkapital."))
    if abs(e["heute"]) >= 0.05:
        saetze.append(f"Heute liegen wir {euro(e['heute'])} im {'Plus' if e['heute'] > 0 else 'Minus'}.")
    else:
        saetze.append("Heute hat sich am Depot noch nichts bewegt.")
    if s.get("gewinnkonto", 0) >= 0.01:
        saetze.append(f"{euro(s['gewinnkonto'])} Gewinn habe ich schon sicher beiseitegelegt.")

    if nb.get("aktiv"):
        saetze.append("Achtung: Die Notbremse ist aktiv. Ich habe alles verkauft und handle erst wieder, "
                      "wenn du mir in Telegram weiter schreibst.")
        return saetze

    # Was halte ich, und wann verkaufe ich?
    for p in s["positionen"]:
        saetze.append(f"Ich halte gerade {p['name']}, seit dem Kauf {plus_minus(p['prozent'])}, "
                      f"also {euro(p['gewinn'])} {'Gewinn' if p['gewinn'] >= 0 else 'Verlust'}.")
        einstand = p["einstandskurs"]
        hoch = max(p.get("hoechstkurs") or einstand, p["kurs"])
        sicherung = einstand * (1 - m["stop_loss"])
        if hoch > einstand:
            sicherung = max(sicherung, hoch * (1 - m["trailing_stop"]))
        saetze.append(f"Mein Ziel: Verkauf mit Gewinn bei {kurs(einstand * (1 + m['take_profit']))}, "
                      f"das wären plus {prozent(m['take_profit'])}. "
                      f"Fällt der Kurs unter {kurs(sicherung)}, verkaufe ich zur Sicherheit.")

    # Was kommt als Nächstes?
    plaetze = m.get("max_positionen") or s["einstellungen"]["max_positionen"]
    if len(s["positionen"]) >= plaetze:
        saetze.append("Mein einziger Platz ist belegt. Neu kaufe ich erst, wenn ich verkauft habe." if plaetze == 1
                      else "Alle Plätze sind belegt. Neu kaufe ich erst, wenn ich etwas verkauft habe.")
    else:
        if not s["positionen"]:
            saetze.append("Gerade habe ich nichts gekauft, das Geld liegt als Bargeld bereit.")
        liste = (s.get("kandidaten") or {}).get("liste") or []
        if m["einstieg"] == "momentum":
            schwelle = m["momentum_min"]
            saetze.append(f"Mein nächstes Ziel: eine Rakete finden. Also einen Wert, der in etwa "
                          f"{round(m['momentum_kerzen'] / 9)} Handelstagen um mindestens {prozent(schwelle)} "
                          "gestiegen ist und dessen Trend weiter nach oben zeigt.")
            bereit = next((k for k in liste if k.get("kaufbereit")), None)
            mit_wert = [k for k in liste if k.get("momentum") is not None]
            if bereit:
                saetze.append(f"{bereit['name']} erfüllt das gerade mit {plus_minus(bereit['momentum'])}. "
                              "Den kaufe ich, sobald die Börse offen ist und meine Regeln es erlauben.")
            elif mit_wert and mit_wert[0]["momentum"] > 0:
                erster = mit_wert[0]
                weitere = [k["name"] for k in mit_wert[1:] if k["momentum"] > 0][:2]
                saetze.append(f"Am nächsten dran ist {erster['name']} mit {plus_minus(erster['momentum'])}. "
                              f"Bis zur Grenze fehlen noch {prozent(schwelle - erster['momentum'])}."
                              + (f" Danach kommen {' und '.join(weitere)}." if weitere else ""))
                if erster["momentum"] < schwelle / 2:
                    saetze.append("Der Markt ist gerade eher ruhig, deshalb warte ich lieber, "
                                  "statt einen schwachen Wert zu kaufen.")
            elif mit_wert:
                saetze.append("Gerade steigt keiner meiner Werte richtig, der Markt ist schwach. "
                              "Ich warte ab und schütze dein Geld.")
        else:
            saetze.append("Ich kaufe, sobald bei einem Wert der schnelle Durchschnitt den langsamen nach oben kreuzt.")
            erster = next((k for k in liste if not k.get("trend_auf")), None)
            if erster:
                saetze.append(f"Am nächsten an so einem Signal ist {erster['name']}.")

    # Börse und Sicherheit
    if not s["boerse_offen"]:
        saetze.append("Die Börse ist gerade zu. Aktien handle ich montags bis freitags von 9 bis halb 6, "
                      "Krypto rund um die Uhr.")
    if nb.get("grenze"):
        luft = s["depotwert"] - nb["grenze"]
        saetze.append(f"Bis zur Notbremse bei {_ganz(nb['grenze'])} Euro sind noch {euro(luft)} Luft."
                      + (" Das ist knapp, ich passe gut auf." if luft < 10 else ""))
    saetze.append("Und wie immer: alles nur Spielgeld.")
    return saetze


async def _sprechen(saetze: list[str], datei: str) -> list[float]:
    """Spricht alle Sätze in eine MP3-Datei. Gibt zurück, ab welcher Sekunde jeder Satz beginnt."""
    import edge_tts
    kommunikation = edge_tts.Communicate(" ".join(saetze), config.LAGE_STIMME, rate=config.LAGE_TEMPO,
                                         boundary="SentenceBoundary")
    anfaenge, gesucht = [], 0
    with open(datei, "wb") as f:
        async for teil in kommunikation.stream():
            if teil["type"] == "audio":
                f.write(teil["data"])
            elif teil["type"] in ("SentenceBoundary", "WordBoundary") and gesucht < len(saetze):
                # Satzanfänge zuordnen, damit die Webseite den gerade gesprochenen Satz hervorheben kann
                if saetze[gesucht].startswith(teil["text"][:12]):
                    anfaenge.append(teil["offset"] / 10_000_000)
                    gesucht += 1
    return anfaenge


def sprachdatei_erzeugen(saetze: list[str], datei: str) -> list[float] | None:
    """Erzeugt die Sprachdatei. Bei jedem Fehler None (dann liest die Webseite selbst vor)."""
    neu = datei + ".neu"
    try:
        anfaenge = asyncio.run(asyncio.wait_for(_sprechen(saetze, neu), ZEITLIMIT))
        if os.path.getsize(neu) < 1000:
            raise ValueError("Sprachdatei ist leer")
        os.replace(neu, datei)
        return anfaenge
    except Exception as fehler:
        print(f"Sprachdatei nicht erzeugt (die Webseite liest dann selbst vor): {fehler!r}")
        if os.path.exists(neu):
            os.remove(neu)
        return None
