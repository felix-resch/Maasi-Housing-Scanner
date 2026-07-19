"""Discord-Webhook-Versand.

Pro neuem Inserat wird eine eigene Nachricht als Embed verschickt (bessere
Uebersicht, jede einzeln anklickbar). Versand per einfachem HTTP-POST, kein
zusaetzliches SDK noetig.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import datetime, timezone

import requests

log = logging.getLogger("watcher")

# Gruen (wie im Plan als Beispiel-Embed-Farbe).
_EMBED_COLOR = 3066993
_MAX_RETRIES = 3

# Discord-API-Basis fuer das Setzen von Reaktionen (nur mit Bot-Token moeglich).
_API_BASE = "https://discord.com/api/v10"

# Quellenname -> anzuzeigende Website.
_WEBSITES = {
    "kamernet": "kamernet.nl",
    "mghousing": "mghousing.nl",
    "wmm": "wmm.nl",
    "maasland": "maaslandrelocation.nl",
    "immoweb": "immoweb.be",
    "huurwoningen": "huurwoningen.nl",
}


def _website_for(listing, source_label: str | None) -> str:
    return _WEBSITES.get(listing.source, source_label or listing.source)


def _iso_to_unix(value) -> int | None:
    """ISO-Zeitstempel -> Unix-Sekunden (fuer Discords dynamische Zeitanzeige)."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def _reaction_legend(reactions: dict | None) -> str | None:
    """Zeile 'Emoji Bedeutung · ...' aus der Reaktions-Config bauen."""
    if not reactions or not reactions.get("enabled", True):
        return None
    if not reactions.get("legend", True):
        return None
    parts = []
    for item in reactions.get("items") or []:
        if isinstance(item, dict) and item.get("emoji"):
            label = item.get("label")
            parts.append(f"{item['emoji']} {label}" if label else str(item["emoji"]))
    return " · ".join(parts) if parts else None


# Sprachen, die jeder Meldung beigelegt werden (Reihenfolge = Anzeige).
_LANGUAGES = [("en", "🇬🇧 English"), ("nl", "🇳🇱 Nederlands")]


def _fill(template, listing) -> str:
    try:
        return str(template).format(
            title=listing.title or "",
            price=listing.price or "",
            url=listing.url or "",
        )
    except (KeyError, IndexError, ValueError):
        # Unbekannter Platzhalter in der Config -> Text unveraendert nehmen.
        return str(template)


def _application_block(listing, application: dict | None) -> str | None:
    """Passende Bewerbungstexte (EN + NL) als kopierbare Code-Bloecke aufbereiten.

    Waehlt je nach erkannter Wohnung (WG-tauglich vs. einzeln) die Variante aus
    der Config und setzt den Platzhalter {title} ein.
    """
    if not application or not application.get("enabled", True):
        return None

    min_bedrooms = int(application.get("min_bedrooms_for_shared", 2))
    shared = listing.is_shared_suitable(min_bedrooms)

    texts = application.get("shared" if shared else "single")
    if not isinstance(texts, dict):
        return None

    if shared:
        bedroom_hint = (
            f" ({listing.bedrooms} Schlafzimmer)" if listing.bedrooms else ""
        )
        label = f"🏠 Mehrzimmer{bedroom_hint} – Vorschlag: eigene WG"
    else:
        label = "🚪 Einzelunterkunft"

    parts = [label, f"➡️ **[Zum Inserat & Bewerben]({listing.url})**"]
    for key, lang_label in _LANGUAGES:
        template = texts.get(key)
        if not template or not str(template).strip():
            continue
        text = _fill(template, listing).strip()
        # Dreifach-Backticks -> Discord zeigt einen Copy-Button.
        parts.append(f"**{lang_label}:**\n```\n{text}\n```")

    # Nur zurueckgeben, wenn mindestens ein Sprachblock vorhanden ist.
    return "\n".join(parts) if len(parts) > 2 else None


def _build_payload(
    listing,
    source_label: str | None,
    application: dict | None,
    reactions: dict | None = None,
) -> dict:
    website = _website_for(listing, source_label)
    embed: dict = {
        "title": (listing.title or "Neues Inserat")[:256],
        "url": listing.url,
        "color": _EMBED_COLOR,
    }

    # Website als erste, gut sichtbare Zeile.
    description_lines = [f"🌐 **{website}**"]
    if listing.price:
        description_lines.append(f"**{listing.price}**")
    if listing.description:
        description_lines.append(listing.description)

    # Online seit: dynamischer Discord-Zeitstempel (zeigt sich in der lokalen
    # Zeit des Betrachters, inkl. relativer Angabe wie "vor 2 Stunden").
    posted_unix = _iso_to_unix(listing.posted_at)
    if posted_unix:
        description_lines.append(f"🕒 Online seit: <t:{posted_unix}:f> (<t:{posted_unix}:R>)")

    app_block = _application_block(listing, application)
    if app_block:
        description_lines.append("")
        description_lines.append(app_block)

    legend = _reaction_legend(reactions)
    if legend:
        description_lines.append(f"\n*{legend}*")

    embed["description"] = "\n".join(description_lines)[:4096]

    if listing.image_url:
        embed["image"] = {"url": listing.image_url}

    # Zeitpunkt, zu dem der Watcher das Inserat gefunden hat (Discord zeigt ihn
    # neben dem Footer an, lokalisiert). Fuer Quellen ohne eigenes Online-Datum
    # ist das der beste Naeherungswert (Poll alle 5 Min).
    embed["timestamp"] = datetime.now(timezone.utc).isoformat()
    embed["footer"] = {"text": f"Quelle: {website} · gefunden"}

    return {"embeds": [embed]}


def _reaction_emojis(reactions: dict | None) -> list[str]:
    """Liste der Reaktions-Emojis aus der Config ziehen (falls aktiviert)."""
    if not reactions or not reactions.get("enabled", True):
        return []
    out: list[str] = []
    for item in reactions.get("items") or []:
        if isinstance(item, dict) and item.get("emoji"):
            out.append(str(item["emoji"]))
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _add_reactions(bot_token, channel_id, message_id, emojis, timeout=15) -> None:
    """Reaktionen an eine bereits gepostete Nachricht setzen (nur mit Bot-Token).

    Reaktionen kann ein Webhook nicht setzen - das geht nur ueber die Discord-API
    mit einem Bot-Token. Fehler pro Emoji werden geloggt, brechen aber nicht ab.
    """
    if not (bot_token and channel_id and message_id):
        return
    headers = {"Authorization": f"Bot {bot_token}"}
    for emoji in emojis:
        enc = urllib.parse.quote(emoji)
        api = (f"{_API_BASE}/channels/{channel_id}/messages/{message_id}"
               f"/reactions/{enc}/@me")
        try:
            r = requests.put(api, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            log.warning("Reaktion %s fehlgeschlagen: %s", emoji, exc)
            continue
        if r.status_code == 429:
            time.sleep(_retry_after_seconds(r))
            try:
                r = requests.put(api, headers=headers, timeout=timeout)
            except requests.RequestException:
                continue
        if r.status_code not in (200, 204):
            log.warning("Reaktion %s -> HTTP %s: %s",
                        emoji, r.status_code, r.text[:150])
        time.sleep(0.3)  # sanftes Rate-Limit fuer Reaktionen


def send_listing(
    webhook_url: str,
    listing,
    source_label: str | None = None,
    timeout: int = 15,
    application: dict | None = None,
    bot_token: str | None = None,
    reactions: dict | None = None,
) -> bool:
    """Ein Listing als Discord-Embed senden und optional Reaktionen setzen.

    Behandelt Rate-Limits (HTTP 429). Wenn ein Bot-Token uebergeben wird und in
    der Config Reaktionen aktiviert sind, werden diese danach an die Nachricht
    gesetzt. Gibt True bei erfolgreichem Versand zurueck (unabhaengig davon, ob
    die Reaktionen klappten), sonst False.
    """
    payload = _build_payload(listing, source_label, application, reactions)

    # wait=true -> Discord liefert die erstellte Nachricht (id + channel_id)
    # zurueck, was wir zum Setzen der Reaktionen brauchen.
    exec_url = webhook_url + ("&" if "?" in webhook_url else "?") + "wait=true"

    message = None
    sent = False
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(exec_url, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            log.warning("Discord-Versand fehlgeschlagen (%s): %s", listing.key, exc)
            return False

        if resp.status_code in (200, 204):
            sent = True
            if resp.status_code == 200:
                try:
                    message = resp.json()
                except ValueError:
                    message = None
            break

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

    if not sent:
        log.warning("Discord-Versand nach %s Versuchen aufgegeben: %s",
                    _MAX_RETRIES, listing.key)
        return False

    emojis = _reaction_emojis(reactions)
    if emojis and bot_token and message:
        _add_reactions(
            bot_token, message.get("channel_id"), message.get("id"), emojis, timeout
        )

    return True


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
