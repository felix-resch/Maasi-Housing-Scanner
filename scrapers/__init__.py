"""Scraper-Paket: pro Quelle ein Modul mit einheitlichem fetch()-Interface."""

from .base import BaseScraper, Listing
from .huurwoningen import HuurwoningenScraper
from .mghousing import MghousingScraper

# Registry: config-Name -> Scraper-Klasse.
# Eine neue Quelle bedeutet: neues Modul + ein Eintrag hier + ein Block in
# config.yaml. main.py bleibt unveraendert (siehe Abschnitt 13 des Plans).
SCRAPERS = {
    HuurwoningenScraper.name: HuurwoningenScraper,
    MghousingScraper.name: MghousingScraper,
}

__all__ = ["BaseScraper", "Listing", "SCRAPERS"]
