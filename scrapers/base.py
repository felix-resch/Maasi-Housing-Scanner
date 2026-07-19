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

    # Fuer die Bewerbungstext-Auswahl (WG vs. einzeln):
    bedrooms: Optional[int] = None      # Anzahl Schlafzimmer, falls bekannt
    property_kind: Optional[str] = None  # z. B. "room", "studio", "apartment", "house"

    # ISO-Zeitstempel, wann das Inserat online ging (falls die Quelle das liefert).
    posted_at: Optional[str] = None

    @property
    def key(self) -> str:
        """Zusammengesetzter Primaerschluessel, z. B. 'huurwoningen:5178b652'."""
        return f"{self.source}:{self.listing_id}"

    def is_shared_suitable(self, min_bedrooms: int = 2) -> bool:
        """True, wenn das Objekt fuer eine eigene WG mit mehreren Personen taugt.

        Kriterium: mindestens `min_bedrooms` Schlafzimmer. Einzelzimmer und
        Studios (property_kind) gelten nie als WG-tauglich.
        """
        if self.property_kind in ("room", "studio"):
            return False
        return self.bedrooms is not None and self.bedrooms >= min_bedrooms


class BaseScraper:
    """Basisklasse. Konkrete Scraper ueberschreiben `name` und `fetch()`."""

    name: str = "base"

    def __init__(self, config: dict):
        # `config` ist der jeweilige Quellen-Block aus config.yaml.
        self.config = config

    def fetch(self) -> list[Listing]:
        """Aktuelle Trefferliste holen und als Liste von Listings zurueckgeben."""
        raise NotImplementedError
