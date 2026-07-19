"""Scraper fuer mghousing.nl.

Die Seite rendert clientseitig (SvelteKit), stellt die Listings aber ueber
eine oeffentliche JSON-API (Payload CMS) bereit:

    GET https://mghousing.nl/api/listings?limit=100

Ein einzelner GET liefert alle Objekte als JSON - kein Playwright noetig.

Relevante Felder pro Objekt:
  id            24-stellige Hex-ObjectId  -> stabile Listing-ID
  title         Strassenname
  address       { street, houseNumber, postalCode, city, ... }
  status        "available" | "rented" | "rented_ur" | ...
  price         { isRentals, isSales, rentals: { amount, ... } }
  media.images  [ { original: "<Bild-URL>", ... }, ... ]

Detail-Link: https://mghousing.nl/en/listings/{rentals|sales}/{id}
"""

from __future__ import annotations

import logging

import requests

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

DETAIL_BASE = "https://mghousing.nl/en/listings"

# mghousing-Typkennungen -> vereinheitlichtes property_kind
_KIND_BY_SUBTYPE = {
    "STUDIO": "studio",
    "STUDENTENKAMER": "room",
    "KAMER": "room",
}
_KIND_BY_MAINTYPE = {
    "HOUSE": "house",
    "APARTMENT": "apartment",
    "ROOM": "room",
}


def _amount(field) -> int | None:
    """Zahl aus einem {isRange, amount}-Feld ziehen, sonst None."""
    if isinstance(field, dict) and isinstance(field.get("amount"), (int, float)):
        return int(field["amount"])
    return None


def _identifier(type_list) -> str | None:
    """identifier des ersten Eintrags einer mainType/subType-Liste."""
    if isinstance(type_list, list) and type_list:
        return type_list[0].get("identifier")
    return None


def _map_kind(main_type: str | None, sub_type: str | None) -> str | None:
    """Vereinheitlichtes property_kind aus mainType/subType ableiten."""
    if sub_type and sub_type in _KIND_BY_SUBTYPE:
        return _KIND_BY_SUBTYPE[sub_type]
    if main_type and main_type in _KIND_BY_MAINTYPE:
        return _KIND_BY_MAINTYPE[main_type]
    return None


class MghousingScraper(BaseScraper):
    name = "mghousing"

    def fetch(self) -> list[Listing]:
        url = self.config.get("url", "https://mghousing.nl/api/listings")
        only_rentals = bool(self.config.get("only_rentals", True))
        only_available = bool(self.config.get("only_available", True))
        cities = [c.strip().lower() for c in self.config.get("cities", []) if c]

        data = self._get(url)
        docs = data.get("docs", [])
        log.info("mghousing: API lieferte %s Objekte", len(docs))

        out: list[Listing] = []
        for doc in docs:
            listing = self._to_listing(
                doc,
                only_rentals=only_rentals,
                only_available=only_available,
                cities=cities,
            )
            if listing is not None:
                out.append(listing)

        log.info("mghousing: %s Objekte nach Filterung", len(out))
        return out

    def _get(self, url: str) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        params = {"limit": 100, "depth": 1}
        resp = requests.get(
            url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def _to_listing(
        self,
        doc: dict,
        *,
        only_rentals: bool,
        only_available: bool,
        cities: list[str],
    ) -> Listing | None:
        price = doc.get("price") or {}
        is_rentals = bool(price.get("isRentals"))

        if only_rentals and not is_rentals:
            return None

        status = str(doc.get("status") or "").lower()
        if only_available and status != "available":
            return None

        address = doc.get("address") or {}
        city = str(address.get("city") or "")
        if cities and city.lower() not in cities:
            return None

        listing_id = doc.get("id")
        if not listing_id:
            return None

        kind = "rentals" if is_rentals else "sales"
        detail_url = f"{DETAIL_BASE}/{kind}/{listing_id}"

        street = address.get("street") or doc.get("title") or ""
        house_no = address.get("houseNumber") or ""
        title = " ".join(p for p in [street, house_no] if p).strip() or "Inserat"

        # Die Website zeigt die Gesamtmiete = Grundmiete + Nebenkosten
        # (z. B. Brusselsestraat 10: 600 + 100 = 700). Daher beides addieren.
        price_str = ""
        rentals = price.get("rentals") or {}
        amount = rentals.get("amount")
        if amount:
            total = int(amount) + int(rentals.get("serviceCharges") or 0)
            price_str = f"€{total:,} p.m.".replace(",", ".")

        image_url = None
        images = (doc.get("media") or {}).get("images") or []
        if images:
            image_url = images[0].get("original")

        # Zimmer-/Typ-Infos fuer die WG-Erkennung.
        details = doc.get("details") or {}
        bedrooms = _amount(details.get("bedrooms"))
        rooms = _amount(details.get("rooms"))
        # Fallback: ohne Schlafzimmerangabe grob ueber Zimmerzahl schaetzen
        # (Zimmer inkl. Wohnzimmer, daher >=3 Zimmer ~ >=2 Schlafzimmer).
        if bedrooms is None and rooms is not None:
            bedrooms = max(rooms - 1, 0) if rooms >= 1 else None
        main_type = _identifier(details.get("type", {}).get("mainType"))
        sub_type = _identifier(details.get("type", {}).get("subType"))
        property_kind = _map_kind(main_type, sub_type)

        postal = address.get("postalCode") or ""
        desc_parts = [p for p in [f"{postal} {city}".strip()] if p.strip()]
        if bedrooms:
            desc_parts.append(f"{bedrooms} bedroom{'s' if bedrooms != 1 else ''}")
        if rentals.get("isFurnished"):
            desc_parts.append("Furnished")
        description = " · ".join(desc_parts) if desc_parts else None

        posted_at = doc.get("publishedAt") or doc.get("createdAt")

        return Listing(
            source=self.name,
            listing_id=str(listing_id),
            url=detail_url,
            title=title,
            price=price_str,
            image_url=image_url,
            description=description,
            bedrooms=bedrooms,
            property_kind=property_kind,
            posted_at=posted_at,
        )
