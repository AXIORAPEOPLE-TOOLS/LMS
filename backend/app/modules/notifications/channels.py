"""Delivery channels. Each channel is a small class with `render` and `send` (SRP/OCP).

No email or WhatsApp provider is connected yet, so those channels are **simulated**:
the full message (to, subject, text, link) is written to the message log
(`delivery_logs`, admin page "Message log") and to the worker console, and nothing
leaves the system. Connecting a real provider = a class with the same `key` whose
`simulated` is False, registered with `register_channel`. Nothing else changes.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.modules.identity.models import User
from app.modules.notifications.models import Notification

logger = logging.getLogger("notifications")


@dataclass(frozen=True)
class Rendered:
    to: str | None  # address; None = cannot be sent on this channel (e.g. no phone number)
    subject: str
    text: str
    missing: str = ""  # why `to` is empty


def _link(notification: Notification) -> str:
    if not notification.link:
        return ""
    return f"{get_settings().public_app_url.rstrip('/')}{notification.link}"


class Channel(Protocol):
    key: str
    label: str
    simulated: bool

    def render(self, user: User, notification: Notification) -> Rendered: ...

    async def send(self, user: User, notification: Notification, message: Rendered) -> str:
        """Return a status: 'sent', 'simulated', 'skipped' or 'failed'."""
        ...


class InAppChannel:
    key = "in_app"
    label = "In app"
    simulated = False

    def render(self, user: User, notification: Notification) -> Rendered:
        return Rendered(to=user.full_name, subject=notification.title, text=notification.body)

    async def send(self, user: User, notification: Notification, message: Rendered) -> str:
        return "sent"  # the notification row itself is the in-app message


class SimulatedEmailChannel:
    key = "email"
    label = "Email"
    simulated = True

    def render(self, user: User, notification: Notification) -> Rendered:
        link = _link(notification)
        text = f"Hi {user.full_name.split()[0]},\n\n{notification.body}".rstrip()
        if link:
            text += f"\n\nOpen: {link}"
        return Rendered(to=user.email, subject=notification.title, text=text)

    async def send(self, user: User, notification: Notification, message: Rendered) -> str:
        logger.info("EMAIL (simulated) to=%s subject=%r", message.to, message.subject)
        return "simulated"


class SimulatedWhatsAppChannel:
    key = "whatsapp"
    label = "WhatsApp"
    simulated = True

    def render(self, user: User, notification: Notification) -> Rendered:
        link = _link(notification)
        text = f"{notification.title}\n{notification.body}".strip()
        if link:
            text += f"\n{link}"
        if not user.phone:
            return Rendered(to=None, subject=notification.title, text=text, missing="No phone number on file")
        return Rendered(to=user.phone, subject=notification.title, text=text)

    async def send(self, user: User, notification: Notification, message: Rendered) -> str:
        logger.info("WHATSAPP (simulated) to=%s text=%r", message.to, message.subject)
        return "simulated"


CHANNELS: dict[str, Channel] = {c.key: c for c in (InAppChannel(), SimulatedEmailChannel(), SimulatedWhatsAppChannel())}


def register_channel(channel: Channel) -> None:
    CHANNELS[channel.key] = channel
