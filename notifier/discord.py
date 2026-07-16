"""Discord-Webhook-Versand.

Pro neuem Inserat wird eine eigene Nachricht als Embed verschickt (bessere
Uebersicht, jede einzeln anklickbar). Versand per einfachem HTTP-POST, kein
zusaetzliches SDK noetig.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("watcher")

# Gruen (wie im Plan als Beispiel-Embed-Farbe).
_EMBED_COLOR = 3066993
_MAX_RETRIES = 3


def _application_block(listing, application: dict | None) -> str | None:
    """Passenden Bewerbungstext als kopierbaren Code-Block aufbereiten.

    Waehlt je nach erkannter Wohnung (WG-tauglich vs. einzeln) die Variante
    aus der Config und setzt die Platzhalter {title}, {price}, {url} ein.
    """
    if not application or not application.get("enabled", True):
        return None

    min_bedrooms = int(application.get("min_bedrooms_for_shared", 2))
    shared = listing.is_shared_suitable(min_bedrooms)

    template = application.get("text_shared" if shared else "text_single")
    if not template or not str(template).strip():
        return None

    try:
        text = str(template).format(
            title=listing.title or "",
            price=listing.price or "",
            url=listing.url or "",
        )
    except (KeyError, IndexError, ValueError):
        # Unbekannter Platzhalter in der Config -> Text unveraendert nehmen.
        text = str(template)

    if shared:
        bedroom_hint = (
            f" ({listing.bedrooms} Schlafzimmer)" if listing.bedrooms else ""
        )
        label = f"🏠 Mehrzimmer{bedroom_hint} – Vorschlag: eigene WG"
    else:
        label = "🚪 Einzelunterkunft"

    # Dreifach-Backticks -> Discord zeigt einen Copy-Button.
    return f"{label}\n**Bewerbungstext (kopieren):**\n```\n{text.strip()}\n```"


def _build_payload(listing, source_label: str | None, application: dict | None) -> dict:
    embed: dict = {
        "title": (listing.title or "Neues Inserat")[:256],
        "url": listing.url,
        "color": _EMBED_COLOR,
    }

    description_lines = []
    if listing.price:
        description_lines.append(f"**{listing.price}**")
    if listing.description:
        description_lines.append(listing.description)

    app_block = _application_block(listing, application)
    if app_block:
        description_lines.append("")
        description_lines.append(f"➡️ **[Zum Inserat & Bewerben]({listing.url})**")
        description_lines.append(app_block)

    if description_lines:
        embed["description"] = "\n".join(description_lines)[:4096]

    if listing.image_url:
        embed["image"] = {"url": listing.image_url}

    embed["footer"] = {"text": f"Quelle: {source_label or listing.source}"}

    return {"embeds": [embed]}


def send_listing(
    webhook_url: str,
    listing,
    source_label: str | None = None,
    timeout: int = 15,
    application: dict | None = None,
) -> bool:
    """Ein Listing als Discord-Embed senden.

    Behandelt Rate-Limits (HTTP 429): wartet die von Discord genannte Zeit ab
    und versucht es erneut. Gibt True bei Erfolg zurueck, sonst False.
    """
    payload = _build_payload(listing, source_label, application)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            log.warning("Discord-Versand fehlgeschlagen (%s): %s", listing.key, exc)
            return False

        if resp.status_code in (200, 204):
            return True

        if resp.status_code == 429:
            retry_after = _retry_after_seconds(resp)
            log.warning(
                "Discord Rate-Limit (429), warte %.1fs (Versuch %s/%s)",
                retry_after,
                attempt,
                _MAX_RETRIES,
            )
            time.sleep(retry_after)
            continue

        log.warning(
            "Discord antwortete mit %s fuer %s: %s",
            resp.status_code,
            listing.key,
            resp.text[:200],
        )
        return False

    log.warning("Discord-Versand nach %s Versuchen aufgegeben: %s",
                _MAX_RETRIES, listing.key)
    return False


def _retry_after_seconds(resp: requests.Response) -> float:
    """Wartezeit aus einer 429-Antwort ermitteln (JSON-Body oder Header)."""
    try:
        data = resp.json()
        if isinstance(data, dict) and "retry_after" in data:
            return float(data["retry_after"]) + 0.5
    except ValueError:
        pass
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header) + 0.5
        except ValueError:
            pass
    return 2.0
