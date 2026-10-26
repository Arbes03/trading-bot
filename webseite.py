"""Die Webseite: zeigt alles übersichtlich im Browser und steuert Bot und Backtest.

Aufruf:  python webseite.py      (öffnet http://localhost:8050 im Browser)
Die Seite ist nur auf diesem PC erreichbar, nicht im Internet.
"""

import json
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import config
from backtest import backtest_ausfuehren
from bot import ZONE, Bot, boerse_offen
from daten import fuer_alle, kurse_laden, marktueberblick
from depot import Depot
from strategie import motor_laden, motor_waehlen
from uebersicht import status_bauen

ORDNER = os.path.dirname(os.path.abspath(__file__))
INDEX_DATEI = os.path.join(ORDNER, "web", "index.html")
LOG_DATEI = os.path.join(ORDNER, "bot.log")
LOG_MAX_BYTES = 2_000_000
AUTOSTART_VERKNUEPFUNG = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu",
                                      "Programs", "Startup", "Trading-Bot.lnk")

sperre = threading.RLock()
protokoll: deque = deque(maxlen=300)
server: ThreadingHTTPServer | None = None


def melden(text: str):
    protokoll.append({"zeit": f"{datetime.now(ZONE):%d.%m. %H:%M}", "text": text})
    print(f"[{datetime.now(ZONE):%d.%m.%Y %H:%M}] {text}", flush=True)


def log_umleiten():
    """Ohne Fenster (Autostart) gehen alle Ausgaben und Fehler in bot.log."""
    if os.path.exists(LOG_DATEI) and os.path.getsize(LOG_DATEI) > LOG_MAX_BYTES:
        os.replace(LOG_DATEI, LOG_DATEI + ".alt")
    datei = open(LOG_DATEI, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = datei


depot = Depot(config.DEPOT_DATEI, config.TRADES_DATEI)
bot = Bot(depot, melden, sperre)

# Kurse für offene Positionen, wenn der Bot gerade keine frischen hat
_kurs_cache: dict[str, tuple[float, float]] = {}
_backtest = {"laeuft": False, "motor": None, "ergebnisse": {}, "fehler": None}
_backtest_sperre = threading.Lock()
_markt: dict[str, dict] = {}


def markt_aktualisieren():
    """Holt im Hintergrund regelmäßig Kurse aller beobachteten Werte für die Übersicht."""
    while True:
        geladen, fehler = fuer_alle(marktueberblick, config.WATCHLIST)
        _markt.update(geladen)
        if fehler:
            print(f"Marktdaten nicht geladen für: {', '.join(fehler)}")
        time.sleep(120 if boerse_offen(datetime.now(ZONE)) else 600)


def aktueller_kurs(ticker: str) -> float | None:
    if ticker in bot.kurse:
        return bot.kurse[ticker]
    if ticker in _markt:
        return _markt[ticker]["kurs"]
    zeitpunkt, kurs = _kurs_cache.get(ticker, (0, None))
    if time.time() - zeitpunkt > 300:
        try:
            kerzen = kurse_laden(ticker, "1d", motor_laden("schnell"))
            kurs = kerzen[-1]["close"] if kerzen else kurs
        except Exception:
            pass
        _kurs_cache[ticker] = (time.time(), kurs)
    return kurs


def status() -> dict:
    with sperre:
        positionen_roh = dict(depot.positionen)
        bargeld = depot.bargeld
    return status_bauen(
        positionen_roh, bargeld,
        kurse={t: aktueller_kurs(t) for t in positionen_roh},
        markt=[_markt[t] for t in config.WATCHLIST if t in _markt],
        protokoll=list(reversed(protokoll)),
        bot_laeuft=bot.laeuft,
        letzte_runde=f"{bot.letzte_runde:%H:%M}" if bot.letzte_runde else None,
        autostart=os.path.exists(AUTOSTART_VERKNUEPFUNG),
        backtest={k: _backtest[k] for k in ("laeuft", "motor", "fehler")},
        pausiert=depot.pausiert,
    )


def backtest_im_hintergrund(name: str):
    if not _backtest_sperre.acquire(blocking=False):
        return
    motor = motor_laden(name)
    _backtest.update(laeuft=True, motor=name, fehler=None)
    melden(f"Backtest gestartet: Motor {motor.titel} ...")
    try:
        _backtest["ergebnisse"][name] = backtest_ausfuehren(motor)
        melden(f"Backtest fertig: Motor {motor.titel}.")
    except Exception as fehler:
        _backtest["fehler"] = str(fehler)
        melden(f"Backtest fehlgeschlagen: {fehler}")
    finally:
        _backtest["laeuft"] = False
        _backtest_sperre.release()


def zuruecksetzen():
    war_aktiv = bot.laeuft
    if war_aktiv:
        bot.stoppen()
    with sperre:
        depot.zuruecksetzen()
    protokoll.clear()
    melden(f"Depot zurückgesetzt auf {config.STARTKAPITAL:,.2f} EUR Spielgeld.")
    if war_aktiv:
        bot.starten()


class Anfrage(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(INDEX_DATEI, "rb") as f:
                self._senden(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._json(status())
        elif self.path == "/api/backtest":
            self._json({**_backtest})
        else:
            self._senden(404, b"Nicht gefunden", "text/plain; charset=utf-8")

    def do_POST(self):
        # Schutz: nur unsere eigene Seite darf Knöpfe auslösen, keine fremde Webseite
        if self.headers.get("X-Trading-Bot") != "1":
            self._senden(403, b"Verboten", "text/plain; charset=utf-8")
            return
        teile = urlsplit(self.path)
        name = parse_qs(teile.query).get("motor", [""])[0]
        if teile.path in ("/api/backtest", "/api/motor") and name not in config.MOTOREN:
            self._senden(400, "Unbekannter Motor".encode("utf-8"), "text/plain; charset=utf-8")
            return

        if teile.path == "/api/bot/start":
            bot.starten()
        elif teile.path == "/api/bot/stop":
            threading.Thread(target=bot.stoppen, daemon=True).start()
        elif teile.path == "/api/backtest":
            threading.Thread(target=backtest_im_hintergrund, args=(name,), daemon=True).start()
        elif teile.path == "/api/motor":
            motor_waehlen(name)
            melden(f"Motor gewechselt: {config.MOTOREN[name]['titel']}. Gilt ab der nächsten Prüfrunde.")
        elif teile.path == "/api/zuruecksetzen":
            zuruecksetzen()
        elif teile.path == "/api/notbremse_aufheben":
            with sperre:
                depot.pausiert = None
                depot.speichern()
            melden("Notbremse aufgehoben, der Bot handelt wieder.")
        elif teile.path == "/api/beenden":
            melden("Bot und Webseite werden beendet.")
            threading.Thread(target=server.shutdown, daemon=True).start()
        else:
            self._senden(404, b"Nicht gefunden", "text/plain; charset=utf-8")
            return
        self._json({"ok": True})

    def _json(self, daten):
        self._senden(200, json.dumps(daten, ensure_ascii=False, default=str).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _senden(self, code, inhalt: bytes, typ: str):
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(inhalt)

    def log_message(self, *args):
        pass  # keine Zeile pro Seitenaufruf im Fenster


def main():
    global server
    # Autostart läuft ohne Fenster (pythonw): dann ins Protokoll schreiben
    if sys.stdout is None or "--hintergrund" in sys.argv:
        log_umleiten()
    adresse = f"http://localhost:{config.WEB_PORT}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", config.WEB_PORT), Anfrage)
    except OSError:
        print(f"Die Webseite läuft schon (oder Port {config.WEB_PORT} ist belegt). Öffne {adresse}")
        if "--ohne-browser" not in sys.argv:
            webbrowser.open(adresse)
        return

    print("=" * 60)
    print(" DEMO-TRADING-BOT  (nur Spielgeld)")
    print(f" Webseite: {adresse}")
    if sys.stdout is sys.__stdout__:
        print(" Dieses Fenster offen lassen. Schließen = Bot aus.")
    else:
        print(" Läuft unsichtbar im Hintergrund. Beenden über die Webseite.")
    print("=" * 60)
    bot.starten()
    threading.Thread(target=markt_aktualisieren, daemon=True).start()
    if "--ohne-browser" not in sys.argv:
        webbrowser.open(adresse)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with sperre:
            depot.speichern()
        print("\nBeendet, Depot gespeichert.")


if __name__ == "__main__":
    main()
