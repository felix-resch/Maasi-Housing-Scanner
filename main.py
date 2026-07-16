"""Wohnungs-Watcher - Einstiegspunkt.

Ablauf pro Durchlauf:
  1. Config + .env laden
  2. je aktivierter Quelle scrapen (Fehler pro Quelle isoliert abgefangen)
  3. gefundene Inserate gegen den SQLite-State abgleichen
  4. fuer wirklich neue Inserate eine Discord-Nachricht senden
  5. State aktualisieren

Baseline: Beim allerersten Lauf einer Quelle (noch keine Eintraege im State)
werden die Funde nur gespeichert, aber KEINE Nachrichten verschickt. Erst ab
dem zweiten Lauf gibt es echte Delta-Benachrichtigungen.

Aufruf:
  python main.py                # ein Durchlauf
  python main.py --dry-run      # ein Durchlauf, aber ohne echten Discord-Versand
  python main.py --loop         # Dauerlauf lokal (poll_interval_minutes)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from notifier import send_listing
from scrapers import SCRAPERS
from storage import State

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
log = logging.getLogger("watcher")


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    # Windows-Konsole ggf. auf UTF-8 stellen, damit € und · nicht crashen.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    file_handler = RotatingFileHandler(
        LOG_DIR / "watcher.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    log.handlers.clear()
    log.addHandler(file_handler)
    log.addHandler(stream_handler)


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_webhook_url(config: dict) -> str | None:
    """Webhook-URL aufloesen. 'ENV:NAME' verweist auf eine Umgebungsvariable."""
    raw = config.get("discord_webhook_url", "")
    if isinstance(raw, str) and raw.startswith("ENV:"):
        return os.environ.get(raw[4:].strip())
    return raw or None


def run_once(config: dict, webhook_url: str | None, dry_run: bool) -> None:
    db_path = ROOT / config.get("state_db", "state.db")
    application = config.get("application")
    state = State(str(db_path))

    total_found = 0
    total_new = 0
    try:
        for source_cfg in config.get("sources", []):
            if not source_cfg.get("enabled", True):
                continue

            name = source_cfg.get("name")
            scraper_cls = SCRAPERS.get(name)
            if scraper_cls is None:
                log.warning("Unbekannte Quelle '%s' in config.yaml, uebersprungen", name)
                continue

            # Baseline pro Quelle: existieren noch keine Eintraege, ist dies der
            # erste (stille) Lauf fuer diese Quelle.
            is_baseline = state.source_count(name) == 0

            try:
                listings = scraper_cls(source_cfg).fetch()
            except requests.RequestException as exc:
                # Erwartbare Netz-/HTTP-Fehler (z. B. huurwoningen 403 durch
                # Cloudflare): knappe Warnung statt Traceback. Lauf laeuft weiter.
                log.warning("Quelle '%s' nicht erreichbar: %s", name, exc)
                continue
            except Exception as exc:  # eine kaputte Quelle darf den Lauf nicht abbrechen
                log.exception("Quelle '%s' fehlgeschlagen: %s", name, exc)
                continue

            total_found += len(listings)
            new_count = 0

            for listing in listings:
                if state.is_seen(listing.key):
                    continue

                new_count += 1

                if is_baseline:
                    # Stiller Baseline-Lauf: speichern, aber nicht benachrichtigen.
                    state.mark_seen(listing, notified=False)
                    continue

                if dry_run:
                    log.info("[dry-run] wuerde senden: %s | %s | %s",
                             listing.title, listing.price, listing.url)
                    state.mark_seen(listing, notified=False)
                    continue

                if not webhook_url:
                    log.error("Keine DISCORD_WEBHOOK_URL gesetzt - kann nicht senden.")
                    state.mark_seen(listing, notified=False)
                    continue

                sent = send_listing(
                    webhook_url, listing, source_label=name, application=application
                )
                state.mark_seen(listing, notified=sent)
                if sent:
                    log.info("Gesendet: %s | %s | %s",
                             listing.title, listing.price, listing.url)

            total_new += new_count
            log.info(
                "Quelle '%s': %s Treffer, %s neu%s",
                name,
                len(listings),
                new_count,
                " (Baseline, still gespeichert)" if is_baseline else "",
            )
    finally:
        state.close()

    log.info("Lauf beendet: %s Treffer gesamt, %s neu gesamt", total_found, total_new)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wohnungs-Watcher")
    parser.add_argument("--dry-run", action="store_true",
                        help="Kein echter Discord-Versand, nur Logging.")
    parser.add_argument("--loop", action="store_true",
                        help="Dauerlauf lokal im poll_interval_minutes-Takt.")
    args = parser.parse_args()

    setup_logging()
    load_dotenv(ROOT / ".env")
    config = load_config()
    webhook_url = resolve_webhook_url(config)

    if not webhook_url and not args.dry_run:
        log.warning("DISCORD_WEBHOOK_URL nicht gesetzt - laeuft nur im Log-Modus.")

    if args.loop:
        interval = int(config.get("poll_interval_minutes", 10)) * 60
        log.info("Loop-Modus: alle %s Minuten", interval // 60)
        while True:
            try:
                run_once(config, webhook_url, args.dry_run)
            except Exception as exc:
                log.exception("Unerwarteter Fehler im Durchlauf: %s", exc)
            time.sleep(interval)
    else:
        run_once(config, webhook_url, args.dry_run)


if __name__ == "__main__":
    main()
