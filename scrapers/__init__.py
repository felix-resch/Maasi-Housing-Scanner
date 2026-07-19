"""Scraper-Paket: pro Quelle ein Modul mit einheitlichem fetch()-Interface."""

from .base import BaseScraper, Listing
from .huurwoningen import HuurwoningenScraper
from .mghousing import MghousingScraper
from .kamernet import KamernetScraper
from .wmm import WmmScraper
from .maasland import MaaslandScraper
from .immoweb import ImmowebScraper

# Registry: config-Name -> Scraper-Klasse.
# Eine neue Quelle bedeutet: neues Modul + ein Eintrag hier + ein Block in
# config.yaml. main.py bleibt unveraendert (siehe Abschnitt 13 des Plans).
SCRAPERS = {
    HuurwoningenScraper.name: HuurwoningenScraper,
    MghousingScraper.name: MghousingScraper,
    KamernetScraper.name: KamernetScraper,
    WmmScraper.name: WmmScraper,
    MaaslandScraper.name: MaaslandScraper,
    ImmowebScraper.name: ImmowebScraper,
}

__all__ = ["BaseScraper", "Listing", "SCRAPERS"]
