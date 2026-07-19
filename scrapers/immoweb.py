"""Scraper fuer immoweb.be (belgische Grenzregion bei Maastricht).

Die Suchergebnisse sind serverseitig gerendert. Jede Karte enthaelt das
komplette Listing als JSON im Attribut :classified eines
<iw-classified-item-bookmark>-Elements - das ist deutlich robuster als das
Auslesen einzelner HTML-Felder.

Wichtige JSON-Felder:
    id
    property.type / subtype / title / bedroomCount / netHabitableSurface
    property.location.{street, postalCode, locality}
    transaction.rental.{monthlyRentalPrice, monthlyRentalCosts}
    media.pictures[].{mediumUrl, smallUrl}

Detail-URL: https://www.immoweb.be/en/classified/<id>

Hinweis: Die in der Config hinterlegte Such-URL enthaelt das gezeichnete
Suchgebiet (geoSearchAreas-Polygon) rund um Maastricht. Immoweb setzt
(inkonsistenten) DataDome-Bot-Schutz ein; ein 403/leeres Ergebnis wird - wie
bei anderen Quellen - pro Lauf toleriert und geloggt.
"""

from __future__ import annotations

import json
import logging

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

DETAIL_BASE = "https://www.immoweb.be/en/classified"

_KIND_MAP = {
    "APARTMENT": "apartment",
    "HOUSE": "house",
    "FLAT_STUDIO": "studio",
    "STUDIO": "studio",
    "GROUND_FLOOR": "apartment",
    "PENTHOUSE": "apartment",
    "DUPLEX": "apartment",
}


class ImmowebScraper(BaseScraper):
    name = "immoweb"

    def fetch(self) -> list[Listing]:
        url = self.config["url"]
        cities = [c.strip().lower() for c in self.config.get("cities", []) if c]

        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        out: list[Listing] = []
        seen: set[str] = set()
        for el in soup.find_all("iw-classified-item-bookmark"):
            raw = el.get(":classified")
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue

            listing = self._to_listing(data)
            if listing is None or listing.listing_id in seen:
                continue
            if cities:
                loc = ((data.get("property") or {}).get("location") or {})
                if str(loc.get("locality") or "").lower() not in cities:
                    continue
            seen.add(listing.listing_id)
            out.append(listing)

        log.info("immoweb: %s Angebote", len(out))
        return out

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en,nl;q=0.8,fr;q=0.6",
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def _to_listing(self, data: dict) -> Listing | None:
        listing_id = data.get("id")
        if not listing_id:
            return None
        listing_id = str(listing_id)

        prop = data.get("property") or {}
        loc = prop.get("location") or {}
        street = loc.get("street") or ""
        postal = loc.get("postalCode") or ""
        locality = loc.get("locality") or ""
        addr = " ".join(p for p in [postal, locality] if p)
        title = ", ".join(p for p in [street, addr] if p) or (prop.get("title") or "Inserat")

        rental = (data.get("transaction") or {}).get("rental") or {}
        price_str = ""
        base = rental.get("monthlyRentalPrice")
        if base:
            total = int(base) + int(rental.get("monthlyRentalCosts") or 0)
            price_str = f"€{total:,} p.m.".replace(",", ".")

        image_url = None
        pics = (data.get("media") or {}).get("pictures") or []
        if pics:
            image_url = pics[0].get("mediumUrl") or pics[0].get("smallUrl")

        bedrooms = prop.get("bedroomCount")
        bedrooms = int(bedrooms) if isinstance(bedrooms, (int, float)) else None
        kind = _KIND_MAP.get(str(prop.get("type") or "").upper())

        desc_parts = []
        if bedrooms:
            desc_parts.append(f"{bedrooms} bedroom{'s' if bedrooms != 1 else ''}")
        surface = prop.get("netHabitableSurface")
        if surface:
            desc_parts.append(f"{int(surface)} m²")
        description = " · ".join(desc_parts) if desc_parts else None

        return Listing(
            source=self.name,
            listing_id=listing_id,
            url=f"{DETAIL_BASE}/{listing_id}",
            title=title,
            price=price_str,
            image_url=image_url,
            description=description,
            bedrooms=bedrooms,
            property_kind=kind,
        )
