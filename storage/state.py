"""SQLite-Zugriff auf den Zustand bereits gesehener Inserate.

Tabelle `seen_listings`:
  id             TEXT PK   zusammengesetzt aus quelle:listing_id
  source         TEXT      Name der Quelle
  listing_id     TEXT      quellenspezifische ID
  url            TEXT      Link zum Inserat
  title          TEXT      Titel/Adresse
  price          TEXT      Preis als Text
  first_seen_at  TEXT      ISO-Timestamp, wann zuerst entdeckt
  notified_at    TEXT      ISO-Timestamp, wann Discord-Nachricht ging (nullable)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_listings (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    listing_id    TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    price         TEXT,
    first_seen_at TEXT NOT NULL,
    notified_at   TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class State:
    def __init__(self, path: str):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def is_seen(self, key: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM seen_listings WHERE id = ?", (key,)
        )
        return cur.fetchone() is not None

    def source_count(self, source: str) -> int:
        """Anzahl bereits gespeicherter Inserate einer Quelle.

        Wird fuer die Baseline-Logik genutzt: ist der Wert 0, ist dies der
        allererste Lauf fuer diese Quelle und es wird still (ohne Discord)
        gespeichert. So flutet auch eine spaeter neu hinzugefuegte Quelle
        nicht den Kanal.
        """
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM seen_listings WHERE source = ?", (source,)
        )
        return int(cur.fetchone()[0])

    def mark_seen(self, listing, notified: bool = False) -> None:
        now = _now()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_listings
                (id, source, listing_id, url, title, price,
                 first_seen_at, notified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing.key,
                listing.source,
                listing.listing_id,
                listing.url,
                listing.title,
                listing.price,
                now,
                now if notified else None,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
