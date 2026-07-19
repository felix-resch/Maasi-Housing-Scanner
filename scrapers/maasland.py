"""Scraper fuer maaslandrelocation.nl.

Serverseitig gerendertes HTML, kein Cloudflare. Alle Angebote unter
/en/properties als Karten:

    <div class="offer">
      <a href="https://maaslandrelocation.nl/en/apartment/<id>/<slug>-maastricht">
        <div class="info"><h2><span class="unit-type">apartment</span> Rechtstraat</h2>
          <div class="location">Maastricht › Wyck</div></div>
        <div class="photo"><figure><img src="...">
          <div class="price">€2,454.21 <small>/month (incl)</small></div>
          <span class="under-option">under option</span></figure></div>
        <div class="specs"><span class="surface">119 m²</span><span class="date">immediate</span></div>
      </a>
    </div>

Die stabile Listing-ID ist das Slug-Segment nach /en/apartment/.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

_ID_RE = re.compile(r"/en/apartment/([^/]+)/")


def _text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


class MaaslandScraper(BaseScraper):
    name = "maasland"

    def fetch(self) -> list[Listing]:
        url = self.config["url"]
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        out: list[Listing] = []
        seen: set[str] = set()
        for card in soup.select(".offer"):
            link = card.select_one('a[href*="/en/apartment/"]')
            if link is None:
                continue
            href = link.get("href", "")
            m = _ID_RE.search(href)
            if not m:
                continue
            listing_id = m.group(1)
            if listing_id in seen:
                continue
            seen.add(listing_id)
            out.append(self._parse_card(card, href, listing_id))

        log.info("maasland: %s Angebote", len(out))
        return out

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en,nl;q=0.8,de;q=0.6",
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def _parse_card(self, card, href: str, listing_id: str) -> Listing:
        unit_type = _text(card.select_one(".unit-type"))
        # h2 enthaelt "<unit-type> <Strasse>" -> Strasse = h2 ohne unit-type
        h2 = _text(card.select_one(".info h2"))
        street = h2
        if unit_type and h2.lower().startswith(unit_type.lower()):
            street = h2[len(unit_type):].strip()
        location = _text(card.select_one(".location"))
        title = ", ".join(p for p in [street, location] if p) or "Inserat"

        # Preis: "€ 2,454.21 /month (incl)" -> "€2,454.21 /month (incl)"
        price = re.sub(r"€\s+", "€", _text(card.select_one(".price")))

        image_url = None
        img = card.select_one(".photo img") or card.select_one("img")
        if img is not None:
            image_url = img.get("src") or img.get("data-src")

        surface = _text(card.select_one(".specs .surface")) or None
        kind = unit_type.lower() or None

        desc_parts = [p for p in [surface, (kind.capitalize() if kind else None)] if p]
        description = " · ".join(desc_parts) if desc_parts else None

        return Listing(
            source=self.name,
            listing_id=listing_id,
            url=href,
            title=title,
            price=price,
            image_url=image_url,
            description=description,
            property_kind=kind,
        )
