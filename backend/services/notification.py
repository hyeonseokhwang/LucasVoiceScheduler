"""Notification channel abstraction.

Provides a pluggable interface for sending notifications through
different channels (WebSocket, Telegram, Email, etc.).
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Base class for notification channels."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier (e.g. 'websocket', 'telegram')."""

    @abstractmethod
    async def send(self, message: dict) -> bool:
        """Send a notification message. Returns True on success."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this channel is currently available."""


class WebSocketChannel(NotificationChannel):
    """WebSocket-based notification channel."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    @property
    def name(self) -> str:
        return "websocket"

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def send(self, message: dict) -> bool:
        if not self._connections:
            return False
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        return True

    async def is_available(self) -> bool:
        return len(self._connections) > 0


class LogChannel(NotificationChannel):
    """Fallback channel that logs notifications (always available)."""

    @property
    def name(self) -> str:
        return "log"

    async def send(self, message: dict) -> bool:
        logger.info(f"[Notification] {message.get('type', 'unknown')}: {message.get('message', '')}")
        return True

    async def is_available(self) -> bool:
        return True


class NotificationManager:
    """Manages multiple notification channels and dispatches messages."""

    def __init__(self):
        self._channels: dict[str, NotificationChannel] = {}

    def register(self, channel: NotificationChannel):
        """Register a notification channel."""
        self._channels[channel.name] = channel
        logger.info(f"[NotificationManager] Registered channel: {channel.name}")

    def unregister(self, name: str):
        """Remove a notification channel."""
        self._channels.pop(name, None)

    def get_channel(self, name: str) -> NotificationChannel | None:
        return self._channels.get(name)

    @property
    def channels(self) -> list[str]:
        return list(self._channels.keys())

    async def broadcast(self, message: dict, channels: list[str] | None = None):
        """Send a notification to all (or specified) channels.

        Args:
            message: The notification payload.
            channels: Optional list of channel names. If None, sends to all.
        """
        targets = channels or list(self._channels.keys())
        results = {}
        for name in targets:
            ch = self._channels.get(name)
            if ch:
                try:
                    if await ch.is_available():
                        results[name] = await ch.send(message)
                    else:
                        results[name] = False
                except Exception as e:
                    logger.warning(f"[NotificationManager] Channel '{name}' error: {e}")
                    results[name] = False
        return results


# Singleton instance
notification_manager = NotificationManager()
