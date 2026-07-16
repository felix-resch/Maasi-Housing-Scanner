"""Scraper fuer kamernet.nl.

Kamernet ist eine Next.js-Seite: die Suchergebnisse stehen server-seitig
gerendert als JSON im <script id="__NEXT_DATA__"> im HTML. Ein einfacher
HTTP-GET (requests) liefert die Daten also direkt - die Seite liegt (anders
als huurwoningen/Pararius) nicht hinter einer Cloudflare-Challenge.

Pfad im JSON:
    props.pageProps.targetPageProps.findListingsResponse.listings

Relevante Felder pro Listing:
    listingId              numerische ID  -> stabile Listing-ID
    listingType            1=room, 4=studio (Kamernet ist v. a. Zimmer/Studios)
    street / streetSlug    Strasse
    city / citySlug        Ort
    surfaceArea            m2
    totalRentalPrice       Miete inkl. (EUR)
    utilitiesIncluded      bool
    resizedFullPreviewImageUrl / fullPreviewImageUrl / thumbnailUrl
    isNewAdvert            zusaetzliches "neu"-Signal

Detail-URL:
    https://kamernet.nl/en/for-rent/{word}-{citySlug}/{streetSlug}/{word}-{id}
"""

from __future__ import annotations

import json
import logging

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

BASE_URL = "https://kamernet.nl"

# listingType -> Wort im Detail-Link. 1 und 4 sind bestaetigt; die uebrigen
# sind Best-Effort. Unbekannte Typen fallen auf "room" zurueck.
_TYPE_WORD = {1: "room", 2: "apartment", 3: "anti-squat", 4: "studio", 5: "house"}


class KamernetScraper(BaseScraper):
    name = "kamernet"

    def fetch(self) -> list[Listing]:
        url = self.config["url"]
        cities = [c.strip().lower() for c in self.config.get("cities", []) if c]

        html = self._get(url)
        listings_raw = self._extract_listings(html)
        log.info("kamernet: %s Listings im HTML", len(listings_raw))

        out: list[Listing] = []
        for raw in listings_raw:
            city = str(raw.get("city") or "")
            if cities and city.lower() not in cities:
                continue
            listing = self._to_listing(raw)
            if listing is not None:
                out.append(listing)

        log.info("kamernet: %s Listings nach Filterung", len(out))
        return out

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en,de;q=0.8,nl;q=0.6",
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _extract_listings(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        node = soup.find("script", id="__NEXT_DATA__")
        if node is None or not node.string:
            return []
        try:
            data = json.loads(node.string)
        except (ValueError, TypeError):
            return []
        try:
            return (
                data["props"]["pageProps"]["targetPageProps"]
                ["findListingsResponse"]["listings"]
            )
        except (KeyError, TypeError):
            return []

    def _to_listing(self, raw: dict) -> Listing | None:
        listing_id = raw.get("listingId")
        if not listing_id:
            return None

        word = _TYPE_WORD.get(raw.get("listingType"), "room")
        city_slug = raw.get("citySlug") or ""
        street_slug = raw.get("streetSlug") or ""
        url = f"{BASE_URL}/en/for-rent/{word}-{city_slug}/{street_slug}/{word}-{listing_id}"

        street = raw.get("street") or ""
        city = raw.get("city") or ""
        title = ", ".join(p for p in [street, city] if p) or "Inserat"

        price_str = ""
        price = raw.get("totalRentalPrice")
        if price:
            price_str = f"€{int(price):,} p.m.".replace(",", ".")

        image_url = (
            raw.get("resizedFullPreviewImageUrl")
            or raw.get("fullPreviewImageUrl")
            or raw.get("thumbnailUrl")
        )

        desc_parts = []
        surface = raw.get("surfaceArea")
        if surface:
            desc_parts.append(f"{surface} m²")
        desc_parts.append(word.capitalize())
        if raw.get("utilitiesIncluded"):
            desc_parts.append("incl. utilities")
        description = " · ".join(desc_parts) if desc_parts else None

        # Kamernet-Objekte im Zimmer/Studio-Filter sind Einzelunterkuenfte.
        bedrooms = 1 if word in ("room", "studio") else None

        return Listing(
            source=self.name,
            listing_id=str(listing_id),
            url=url,
            title=title,
            price=price_str,
            image_url=image_url,
            description=description,
            bedrooms=bedrooms,
            property_kind=word,
        )
