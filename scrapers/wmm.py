"""Scraper fuer wmm.nl (Woningmakelaardij Maastricht).

Serverseitig gerendertes HTML, kein Cloudflare. Ergebniskarten unter /en/offers:

    <a class="item" href="https://wmm.nl/en/offers/maastricht/<slug>/<id>">
      <div class="img"><img src="..."><div class="price">€597,00 <span>/ month (incl.)</span></div></div>
      <div class="street">Baron van Hovellstraat 71</div>
      <div class="place">Maastricht</div>
      <div class="bottom">
        <div><i class="hms-size"></i> 18 m²</div>
        <div><i class="hms-bedroom"></i> 1</div>
        <div><i class="hms-room"></i> Room</div>
        <div><i class="hms-calendar"></i> 01-08-2026</div>
      </div>
    </a>

Die stabile Listing-ID ist das numerische Segment am Ende des Detail-Links.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

_ID_RE = re.compile(r"/(\d+)/?$")


def _text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


class WmmScraper(BaseScraper):
    name = "wmm"

    def fetch(self) -> list[Listing]:
        url = self.config["url"]
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        out: list[Listing] = []
        seen: set[str] = set()
        for card in soup.select("a.item[href]"):
            href = card.get("href", "")
            m = _ID_RE.search(href.split("?")[0])
            if not m:
                continue
            listing_id = m.group(1)
            if listing_id in seen:
                continue
            seen.add(listing_id)
            out.append(self._parse_card(card, href, listing_id))

        log.info("wmm: %s Angebote", len(out))
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
        street = _text(card.select_one(".street"))
        place = _text(card.select_one(".place"))
        title = ", ".join(p for p in [street, place] if p) or "Inserat"

        price = re.sub(r"€\s+", "€", _text(card.select_one(".price")))

        image_url = None
        img = card.select_one(".img img")
        if img is not None:
            image_url = img.get("src") or img.get("data-src")

        # .bottom-Felder anhand ihrer Icon-Klassen zuordnen.
        bedrooms = None
        surface = None
        kind = None
        for div in card.select(".bottom > div"):
            icon = div.find("i")
            icon_cls = " ".join(icon.get("class", [])) if icon else ""
            value = _text(div)
            if "hms-bedroom" in icon_cls:
                m = re.search(r"\d+", value)
                bedrooms = int(m.group()) if m else None
            elif "hms-size" in icon_cls:
                surface = value
            elif "hms-room" in icon_cls:
                kind = value.lower() or None

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
            bedrooms=bedrooms,
            property_kind=kind,
        )
