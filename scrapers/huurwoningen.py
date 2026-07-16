"""Scraper fuer huurwoningen.nl (serverseitig gerendert, HTML per HTTP-GET).

Struktur einer Ergebnis-Karte (Stand der Recherche):
  <section class="listing-search-item" ...>
    <a class="listing-search-item__link--title"
       href="/en/huren/maastricht/0527bf99/rechtstraat/">Flat Rechtstraat</a>
    <div class="listing-search-item__sub-title">6221 EG Maastricht (Wyck)</div>
    <div class="listing-search-item__price">EUR 1,175 pcm</div>
    <div class="illustrated-features__item">50 m2</div> ...
    <img src="https://.../foo.jpg?width=600&auto=webp">
    <span class="listing-label--new">New</span>

Die stabile Listing-ID ist das Hex-Segment im URL-Pfad (hier: 0527bf99).
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger("watcher")

BASE_URL = "https://www.huurwoningen.nl"

# Hex-Segment nach dem Stadt-Teil im Detail-Link, z. B.
# /en/huren/maastricht/0527bf99/rechtstraat/ -> 0527bf99
_ID_RE = re.compile(r"/huren/[^/]+/([0-9a-fA-F]{6,})(?:/|$)")


def _text(node) -> str:
    """Textinhalt eines BeautifulSoup-Knotens, Whitespace normalisiert."""
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(strip=True)).strip()


class HuurwoningenScraper(BaseScraper):
    name = "huurwoningen"

    def fetch(self) -> list[Listing]:
        base = self.config["url"]
        pages = int(self.config.get("pages", 1))

        listings: list[Listing] = []
        seen_ids: set[str] = set()

        for page in range(1, pages + 1):
            page_url = base if page == 1 else self._with_page(base, page)
            html = self._get(page_url)
            if not html:
                continue
            page_listings = self._parse(html, seen_ids)
            log.info("huurwoningen: Seite %s -> %s Karten", page, len(page_listings))
            listings.extend(page_listings)

        return listings

    @staticmethod
    def _with_page(url: str, page: int) -> str:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en,de;q=0.8,nl;q=0.6",
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def _parse(self, html: str, seen_ids: set[str]) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[Listing] = []

        for card in soup.select("section.listing-search-item"):
            link = (
                card.select_one("a.listing-search-item__link--title")
                or card.select_one("a.listing-search-item__link--depiction")
                or card.select_one("a.listing-search-item__link")
            )
            if link is None:
                continue

            href = link.get("href", "")
            match = _ID_RE.search(href)
            if not match:
                continue

            listing_id = match.group(1).lower()
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            full_url = href if href.startswith("http") else BASE_URL + href
            title = _text(card.select_one(".listing-search-item__title")) or _text(link)
            subtitle = _text(card.select_one(".listing-search-item__sub-title"))
            price = _text(card.select_one(".listing-search-item__price"))

            features = [
                _text(item)
                for item in card.select(".illustrated-features__item")
                if _text(item)
            ]

            image_url = None
            img = card.select_one("img")
            if img is not None:
                image_url = img.get("src") or img.get("data-src")

            desc_parts = [p for p in [subtitle, *features] if p]
            description = " · ".join(desc_parts) if desc_parts else None

            out.append(
                Listing(
                    source=self.name,
                    listing_id=listing_id,
                    url=full_url,
                    title=title or "Inserat",
                    price=price,
                    image_url=image_url,
                    description=description,
                )
            )

        return out
