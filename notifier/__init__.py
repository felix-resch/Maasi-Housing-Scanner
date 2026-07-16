"""Notifier-Paket: Versand neuer Inserate an einen Discord-Webhook."""

from .discord import send_listing

__all__ = ["send_listing"]
