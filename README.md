# Wohnungs-Watcher

Kleines Tool, das niederländische Wohnungsportale regelmäßig auf neue Inserate
in **Maastricht** prüft und bei einem neuen Fund sofort eine **Discord-Webhook**-
Nachricht mit dem Link auslöst.

Quellen:

| Quelle | Zugriff | Status |
|---|---|---|
| [kamernet.nl](https://kamernet.nl/en/for-rent/properties-maastricht) | `__NEXT_DATA__`-JSON im HTML | ✅ funktioniert (v. a. Zimmer/Studios) |
| [mghousing.nl](https://mghousing.nl/en/listings) | JSON-API `/api/listings` (Payload CMS) | ✅ funktioniert |
| [wmm.nl](https://wmm.nl/en/offers) | HTML-Parsing (`a.item`-Karten) | ✅ funktioniert |
| [maaslandrelocation.nl](https://maaslandrelocation.nl/en/properties) | HTML-Parsing (`.offer`-Karten) | ✅ funktioniert |
| [immoweb.be](https://www.immoweb.be) | eingebettetes `:classified`-JSON pro Karte | ✅ funktioniert (belgische Grenzregion) |
| [huurwoningen.nl](https://www.huurwoningen.nl/en/in/maastricht/) | HTML-Parsing (serverseitig) | ⛔ Cloudflare-Challenge – Scraper drin, wird pro Lauf still übersprungen |

> **Keine Browser-Automatisierung (Playwright) nötig** – jede aktive Quelle liefert
> die Daten per einfachem HTTP-GET (JSON-API, eingebettetes JSON oder HTML).
>
> **immoweb.be** deckt die belgischen Nachbargemeinden (Lanaken, Riemst,
> Bilzen, Vlijtingen …) über das in der Such-URL gespeicherte Gebiets-Polygon ab.
> Immoweb setzt (inkonsistenten) DataDome-Bot-Schutz ein; ein evtl. leeres/
> geblocktes Ergebnis wird pro Lauf toleriert. Auf GitHub-Actions-IPs kann die
> Trefferquote schwanken.
>
> **huurwoningen.nl** steht hinter einer Cloudflare-Bot-Challenge
> (`cf-mitigated: challenge`). Ein einfacher HTTP-Client kommt dort nicht durch;
> das Umgehen von Cloudflare ist ein bewusstes Nicht-Ziel. Der Scraper bleibt
> registriert (falls sich das Verhalten ändert) und wird bei einem 403 mit einer
> einzeiligen Warnung übersprungen. (Pararius: ebenfalls Cloudflare.)

## Funktionsweise

Jeder Durchlauf holt die aktuelle Trefferliste je Quelle, vergleicht die
gefundenen Listing-IDs gegen den gespeicherten Zustand (`state.db`, SQLite),
verschickt nur für **wirklich neue** IDs eine Discord-Nachricht und aktualisiert
danach den Zustand.

**Baseline:** Beim allerersten Lauf einer Quelle wird der State nur gefüllt,
ohne Nachrichten zu verschicken (sonst würden alle ~190 Bestandsinserate auf
einmal gemeldet). Echte Benachrichtigungen gibt es ab dem zweiten Lauf.

## Projektstruktur

```
wohnungs-watcher/
├── config.yaml            # Quellen, Filter, Intervall
├── .env.example           # Vorlage für die Webhook-URL (nach .env kopieren)
├── requirements.txt
├── main.py                # Einstiegspunkt, ein Durchlauf pro Aufruf
├── test_discord.py        # isolierter Webhook-Test
├── scrapers/
│   ├── base.py            # Listing-Datenmodell + Scraper-Interface
│   ├── kamernet.py        # __NEXT_DATA__-JSON-Parser
│   ├── mghousing.py       # JSON-API-Client
│   └── huurwoningen.py    # HTML-Parser (aktuell Cloudflare-geblockt)
├── storage/state.py       # SQLite: is_seen(), mark_seen(), Baseline
├── notifier/discord.py    # Embed-Versand inkl. 429-Retry
├── logs/watcher.log       # entsteht automatisch
└── .github/workflows/watch.yml
```

## Voraussetzungen

- **Python 3.12** (auf diesem Rechner bereits installiert unter
  `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`)
- `pip install -r requirements.txt` (Abhängigkeiten bereits installiert)

## Lokal einrichten und testen

```bash
# 1. Abhängigkeiten
pip install -r requirements.txt

# 2. Webhook-URL hinterlegen
cp .env.example .env
#   -> DISCORD_WEBHOOK_URL in .env eintragen

# 3. Webhook isoliert testen
python test_discord.py

# 4. Trockenlauf ohne echten Versand (loggt nur, was gesendet würde)
python main.py --dry-run

# 5. Echter Einzeldurchlauf
python main.py

# 6. Optional: Dauerlauf lokal (poll_interval_minutes aus config.yaml)
python main.py --loop
```

### State-Logik testen

1. `state.db` löschen
2. `python main.py` → **Baseline**, es kommt keine Nachricht
3. `python main.py` → ohne neue Daten wieder keine Nachricht
4. In `state.db` einen Eintrag löschen (z. B. per DB Browser for SQLite)
5. `python main.py` → genau dafür kommt eine Nachricht

## Discord-Webhook anlegen

Discord-Kanal → **Kanaleinstellungen → Integrationen → Webhooks → Neuer
Webhook** → URL kopieren. Diese URL kommt in `.env` (lokal) bzw. als
GitHub-Actions-Secret (Deployment). **Niemals im Code hartcodieren.**

## Deployment über GitHub Actions

Das Anlegen des Repositories und das Eintragen des Secrets müssen **einmalig von
dir selbst** im GitHub-Interface gemacht werden (ein Secret trägt grundsätzlich
nur der Kontoinhaber ein).

1. **Repository anlegen** – auf github.com ein Repo `wohnungs-watcher` erstellen
   (öffentlich oder privat – siehe **Kosten & Intervall** unten).
2. **Projekt hochladen** (das lokale Git-Repo ist bereits initialisiert und
   committet – nur noch Remote setzen und pushen):
   ```bash
   git remote add origin https://github.com/<dein-username>/wohnungs-watcher.git
   git push -u origin main
   ```
3. **Secret hinterlegen** – Repo → *Settings → Secrets and variables → Actions →
   New repository secret* → Name `DISCORD_WEBHOOK_URL`, Value = deine Webhook-URL.
4. **Workflow** liegt bereits unter `.github/workflows/watch.yml` (Lauf alle
   5 Minuten, UTC) und wird beim Push mit hochgeladen.
5. **Testen** – Tab *Actions* → *Wohnungs-Watcher* → *Run workflow*. Beim ersten
   Lauf (Baseline) kommt bewusst noch keine Discord-Nachricht.

Der Workflow committet die aktualisierte `state.db` nach jedem Lauf zurück ins
Repo, damit der Zustand zwischen den Läufen erhalten bleibt.

### Kosten & Intervall (wichtig)

GitHub rechnet Actions-Zeit **pro Job auf die nächste volle Minute aufgerundet**.
Ein Lauf dauert nur Sekunden, zählt aber als **1 Minute**.

- **Öffentliches Repo:** Actions sind **komplett gratis und unbegrenzt** →
  5-Minuten-Takt problemlos. Nachteil: Code inkl. `config.yaml` (mit deinem
  Namen/Anschreiben) und `state.db`/Logs sind öffentlich sichtbar.
- **Privates Repo:** Gratis-Kontingent **2.000 Minuten/Monat**. Bei alle 5 Min
  (~8.640 Läufe/Monat) wird das **weit überschritten** – auch alle 10 Min
  (~4.320) liegt darüber. Unter 2.000 bleibt man erst ab **ca. alle 30 Minuten**
  (`*/30`). Über dem Kontingent pausiert GitHub einfach, es sei denn, du hast ein
  Zahlungsmittel + Ausgabenlimit > 0 hinterlegt (dann ~0,008 $/Min).

**Empfehlung für 5-Minuten-Takt gratis:** öffentliches Repo mit unauffälligem
Namen. Wer privat bleiben will, setzt in `watch.yml` `cron: "*/30 * * * *"`.

## Konfiguration (`config.yaml`)

- `poll_interval_minutes` – nur für den lokalen `--loop`-Modus.
- `sources[].url` – bei huurwoningen kann direkt eine vorgefilterte Such-URL
  hinterlegt werden (z. B. `.../en/in/maastricht/?price=450-650`).
- `sources[].pages` – Anzahl abgefragter Ergebnisseiten (Standard 1).
- mghousing: `only_rentals`, `only_available`, `cities` – Filter für Miet-
  bzw. verfügbare Objekte und Städte.

### Bewerbungstext (`application`)

Jeder Discord-Meldung wird ein fertiger Bewerbungstext als **kopierbarer
Code-Block** (Discord zeigt dazu einen Copy-Button) plus ein „Zum Inserat &
Bewerben"-Link beigelegt. Das Tool erkennt automatisch, ob es sich um eine
**Einzelunterkunft** (Zimmer, Studio, 1-Schlafzimmer-Wohnung) oder ein
**Mehrzimmer-Objekt** (≥ `min_bedrooms_for_shared` Schlafzimmer, also für eine
eigene WG mit Freund:in geeignet) handelt, und wählt entsprechend `text_single`
oder `text_shared`. Platzhalter `{title}`, `{price}`, `{url}` werden ersetzt.

Die Schlafzimmerzahl kommt bei mghousing aus `details.bedrooms`; Kamernet-Zimmer
und -Studios gelten immer als Einzelunterkunft. Fehlt die Angabe, wird
sicherheitshalber `text_single` verwendet.

## Abschaltung nach Ende der Nutzung

- GitHub-Actions-Workflow deaktivieren oder Repo archivieren/löschen
- Discord-Webhook im Kanal löschen
- lokale `.env` mit der Webhook-URL löschen

## Hinweise / Risiken

- Strukturänderungen an den Zielseiten können einen Parser brechen; das Logging
  (`logs/watcher.log`) zeigt pro Lauf Trefferzahlen je Quelle.
- Höfliches Verhalten: erkennbarer User-Agent, moderates Poll-Intervall.
- Scraping bewegt sich AGB-seitig in einer Grauzone; für kurzzeitigen, privaten,
  nicht-kommerziellen Gebrauch mit moderater Frequenz ist das praktische Risiko
  gering – das ist keine Rechtsberatung.
