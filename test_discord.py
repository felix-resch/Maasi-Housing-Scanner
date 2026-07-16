"""Kleiner Verbindungstest fuer den Discord-Webhook (Plan, Abschnitt 10).

Schickt eine einzelne Testnachricht an die in .env hinterlegte Webhook-URL,
bevor der volle Workflow getestet wird.

    python test_discord.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from notifier import send_listing
from scrapers.base import Listing

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL ist nicht gesetzt (.env pruefen).")
        sys.exit(1)

    demo = Listing(
        source="test",
        listing_id="0",
        url="https://www.huurwoningen.nl/en/in/maastricht/",
        title="Testnachricht Wohnungs-Watcher",
        price="€0 pcm",
        description="Wenn du das siehst, funktioniert der Webhook. ✅",
        image_url=None,
    )

    ok = send_listing(webhook_url, demo, source_label="test_discord.py")
    print("Gesendet ✅" if ok else "Fehlgeschlagen ❌ (siehe Ausgabe oben)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
