"""Telegram notification channel.

Sends notifications via Telegram Bot API.
Activated when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars are set.
"""

import os
import logging

import httpx

from services.notification import NotificationChannel

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


class TelegramChannel(NotificationChannel):
    """Telegram Bot API notification channel."""

    def __init__(self, token: str = "", chat_id: str = ""):
        self._token = token or TELEGRAM_BOT_TOKEN
        self._chat_id = chat_id or TELEGRAM_CHAT_ID
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "telegram"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def is_available(self) -> bool:
        return bool(self._token and self._chat_id)

    async def send(self, message: dict) -> bool:
        if not await self.is_available():
            logger.debug("[Telegram] Not configured (missing token or chat_id)")
            return False

        text = self._format_message(message)
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"

        try:
            client = self._get_client()
            resp = await client.post(url, json={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
            })
            if resp.status_code == 200:
                logger.info(f"[Telegram] Sent: {message.get('type', 'unknown')}")
                return True
            else:
                logger.warning(f"[Telegram] API error {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.warning(f"[Telegram] Send failed: {e}")
            return False

    def _format_message(self, message: dict) -> str:
        """Format notification message for Telegram."""
        msg_type = message.get("type", "notification")
        text = message.get("message", "")

        if msg_type == "reminder":
            schedule = message.get("schedule", {})
            return (
                f"<b>📅 일정 알림</b>\n\n"
                f"{text}\n\n"
                f"카테고리: {schedule.get('category', 'general')}"
            )
        elif msg_type == "challenge_reminder":
            return (
                f"<b>🏆 챌린지 알림</b>\n\n"
                f"{text}\n\n"
                f"D-{message.get('d_day', '?')}"
            )
        elif msg_type == "milestone_reminder":
            return (
                f"<b>🎯 마일스톤 알림</b>\n\n"
                f"{text}"
            )
        elif msg_type == "webhook":
            event = message.get("event", "unknown")
            return (
                f"<b>🔔 {event}</b>\n\n"
                f"{text}"
            )
        else:
            return f"<b>📢 알림</b>\n\n{text}"
