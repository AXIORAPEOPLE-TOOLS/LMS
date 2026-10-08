"""Delivery channels. Each channel is a small class with one `send` method (SRP/OCP).

Email and WhatsApp only log until real provider APIs are configured; adding a
provider means adding a class here and registering it — nothing else changes.
"""

import logging
from typing import Protocol

from app.modules.identity.models import User
from app.modules.notifications.models import Notification

logger = logging.getLogger("notifications")


class Channel(Protocol):
    key: str

    async def send(self, user: User, notification: Notification) -> str:
        """Return a status: 'sent', 'skipped' or 'failed'."""
        ...


class InAppChannel:
    key = "in_app"

    async def send(self, user: User, notification: Notification) -> str:
        return "sent"  # the row itself is the in-app message


class LogEmailChannel:
    key = "email"

    async def send(self, user: User, notification: Notification) -> str:
        logger.info("EMAIL to=%s subject=%r", user.email, notification.title)
        return "sent"


class LogWhatsAppChannel:
    key = "whatsapp"

    async def send(self, user: User, notification: Notification) -> str:
        logger.info("WHATSAPP to=%s text=%r", user.email, notification.title)
        return "sent"


CHANNELS: dict[str, Channel] = {c.key: c for c in (InAppChannel(), LogEmailChannel(), LogWhatsAppChannel())}


def register_channel(channel: Channel) -> None:
    CHANNELS[channel.key] = channel
