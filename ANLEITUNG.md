# Demo-Trading-Bot (Spielgeld)

Ein Bot, der 48 Werte beobachtet (alle DAX-Aktien und 8 große Index-ETFs) und mit **10.000 € Spielgeld** automatisch kauft und verkauft.
Er ist kostenlos, braucht keine Anmeldung bei einem Broker und nutzt **kein echtes Geld**. Er ist keine Anlageberatung.

Es gibt zwei Arten, ihn laufen zu lassen:

| | Auf deinem PC | Bei GitHub (Cloud) |
|---|---|---|
| Läuft, wenn der PC aus ist | nein | **ja** |
| Webseite | `http://localhost:8050` (nur dieser PC) | `https://DEINNAME.github.io/trading-bot/` (überall, auch Handy) |
| Bedienen (Start/Stopp, Backtest, Motor wechseln) | ja, auf der Webseite | nur zuschauen; Änderungen über Dateien bei GitHub |

---

## A) Auf deinem PC

| Datei (Doppelklick) | Was sie macht |
|---|---|
| `START` | Startet Bot und Webseite und öffnet die Seite im Browser (oder öffnet nur die Seite, wenn der Bot schon läuft) |
| `autostart_einschalten` | Bot und Webseite starten nach jedem Hochfahren automatisch, unsichtbar im Hintergrund |
| `autostart_ausschalten` | Schaltet den Autostart wieder aus |

- Beenden: auf der Webseite unter *Strategie & Einstellungen* → **Bot & Webseite beenden**
- Was passiert ist, steht in `bot.log`
- Der PC darf nicht in den Energiesparmodus gehen (*Einstellungen → System → Energie*)

## B) Bei GitHub, damit der Bot läuft, wenn der PC aus ist

GitHub führt den Bot **alle 15 Minuten** aus (Mo–Fr während der Börsenzeit) und veröffentlicht die Webseite.
Kosten: 0 €. Du brauchst nur ein kostenloses GitHub-Konto.

1. **Konto anlegen:** auf [github.com](https://github.com) auf *Sign up* klicken (kostenlos).
2. **Neues Projekt anlegen:** oben rechts **+** → *New repository*
   - Name: `trading-bot`
   - Sichtbarkeit: **Public**. Nur dann ist die Webseite kostenlos. Sichtbar ist dann der Code und das Spielgeld-Depot, keine persönlichen Daten. Dein GitHub-Benutzername steht aber in der Adresse.
   - Sonst nichts ankreuzen → *Create repository*
3. **Hochladen:** Gib Claude die Adresse des Projekts (z. B. `https://github.com/DEINNAME/trading-bot`). Claude lädt alles hoch. Dabei öffnet sich einmal ein Browserfenster, in dem du dich bei GitHub anmeldest.
4. **Webseite einschalten:** im Projekt bei GitHub *Settings* → *Pages* → bei *Source* **GitHub Actions** auswählen.
5. **Ersten Lauf starten:** Reiter *Actions* → falls gefragt, Workflows erlauben → links **Trading-Bot (Spielgeld)** → **Run workflow**.
   Nach 1–2 Minuten ist die Webseite unter `https://DEINNAME.github.io/trading-bot/` erreichbar.
6. **PC-Bot ausschalten:** Damit nicht zwei Bots mit zwei verschiedenen Depots handeln: Doppelklick auf `autostart_ausschalten` und auf der lokalen Webseite *Bot & Webseite beenden*.

**Bei GitHub etwas ändern** (im Projekt auf die Datei klicken → Stift-Symbol → *Commit changes*):
- Motor wechseln: Datei `motor.txt` → `vorsichtig` oder `schnell` hineinschreiben
- Von vorn anfangen: Dateien `trades.csv`, `verlauf.csv`, `protokoll.json` löschen und in `depot.json` den Inhalt durch `{"bargeld": 10000.0, "positionen": {}}` ersetzen

Gut zu wissen: GitHub startet geplante Läufe manchmal ein paar Minuten zu spät. Für diesen Bot ist das egal.

---

## Die Strategie-Motoren

| Motor | Wie er handelt |
|---|---|
| **Vorsichtig** (Standard) | Stundenkerzen, kauft nur in längeren Aufwärtstrends, darf über Nacht halten, höchstens 2 Käufe pro Tag, wenige Trades |
| **Schnell (Daytrading)** | 5-Minuten-Kerzen, reagiert auf jede kleine Bewegung, verkauft abends alles, sehr viele Trades |

Alle Zahlen stehen in `config.py`. Nach Änderungen immer zuerst einen Backtest machen (lokale Webseite → *Backtest*).

Backtest-Ergebnisse (Stand Oktober 2026, ohne Steuern):

| Motor | Zeitraum | Bot | Einfach kaufen & halten |
|---|---|---|---|
| Schnell | 60 Tage | −38,8 % | −2,1 % |
| Vorsichtig | dieselben 60 Tage | −8,2 % | −2,2 % |
| Vorsichtig | 2 Jahre | +13,5 % | +28,9 % |

Vergangene Ergebnisse garantieren nichts für die Zukunft.

## Dateien

| Datei | Inhalt |
|---|---|
| `config.py` | Alle Einstellungen: Werte, Kosten, Risiko, Motoren |
| `strategie.py` | Kauf- und Verkaufsregeln der Motoren |
| `depot.py` | Spielgeld-Konto und Trade-Protokoll |
| `handel.py` | Gemeinsame Handelslogik |
| `daten.py` | Kursabruf von Yahoo Finance (ca. 15 Minuten verzögert) |
| `bot.py` | Der Bot, der dauerhaft auf dem PC läuft |
| `backtest.py` | Test an vergangenen Kursen (`python backtest.py` vergleicht beide Motoren) |
| `webseite.py`, `web/index.html` | Die Webseite |
| `uebersicht.py` | Berechnet, was die Webseite anzeigt (PC und Cloud gleich) |
| `cloud_runde.py`, `.github/workflows/bot.yml` | Die Cloud-Version für GitHub |
| `depot.json`, `trades.csv`, `verlauf.csv` | Der gespeicherte Stand (zum Neustart löschen bzw. zurücksetzen) |
