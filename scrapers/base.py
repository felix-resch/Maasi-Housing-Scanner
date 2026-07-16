"""Gemeinsames Interface fuer alle Scraper.

Jede Quelle liefert eine Liste von `Listing`-Objekten. Der Rest des Programms
(State, Notifier) kennt keinerlei seitenspezifische Details mehr - dadurch
laesst sich eine neue Quelle sauber anhaengen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Erkennbarer, hoeflicher User-Agent (siehe Abschnitt 12 des Plans).
USER_AGENT = (
    "wohnungs-watcher/1.0 (private, non-commercial apartment search; "
    "polite polling)"
)

REQUEST_TIMEOUT = 20


@dataclass
class Listing:
    """Ein einzelnes Inserat in einheitlicher Form."""

    source: str          # Name der Quelle, z. B. "huurwoningen"
    listing_id: str      # quellenspezifische, stabile ID
    url: str             # vollstaendiger Link zum Inserat
    title: str           # Titel/Adresse
    price: str = ""      # Preis als Text (Format variiert je Seite)
    image_url: Optional[str] = None
    description: Optional[str] = None  # Zusatzinfos fuer das Discord-Embed

    @property
    def key(self) -> str:
        """Zusammengesetzter Primaerschluessel, z. B. 'huurwoningen:5178b652'."""
        return f"{self.source}:{self.listing_id}"


class BaseScraper:
    """Basisklasse. Konkrete Scraper ueberschreiben `name` und `fetch()`."""

    name: str = "base"

    def __init__(self, config: dict):
        # `config` ist der jeweilige Quellen-Block aus config.yaml.
        self.config = config

    def fetch(self) -> list[Listing]:
        """Aktuelle Trefferliste holen und als Liste von Listings zurueckgeben."""
        raise NotImplementedError
