"""Webhook service for external integrations.

Dispatches events (schedule created, completed, reminder) to registered
webhook URLs via HTTP POST.
"""

import asyncio
import json
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Webhook URLs from env (comma-separated)
WEBHOOK_URLS = [
    u.strip()
    for u in os.environ.get("SCHEDULER_WEBHOOK_URLS", "").split(",")
    if u.strip()
]


class WebhookService:
    """Manages webhook dispatching."""

    def __init__(self):
        self._urls: list[str] = list(WEBHOOK_URLS)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def add_url(self, url: str):
        if url not in self._urls:
            self._urls.append(url)

    def remove_url(self, url: str):
        if url in self._urls:
            self._urls.remove(url)

    async def dispatch(self, event: str, data: dict):
        """Dispatch a webhook event to all registered URLs.

        Args:
            event: Event type (e.g. 'schedule.created', 'schedule.completed', 'reminder')
            data: Event payload
        """
        if not self._urls:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        client = self._get_client()
        tasks = [self._send(client, url, payload) for url in self._urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send(self, client: httpx.AsyncClient, url: str, payload: dict):
        try:
            resp = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "LucasScheduler/1.0"},
            )
            logger.info(f"[Webhook] {payload['event']} → {url} ({resp.status_code})")
        except Exception as e:
            logger.warning(f"[Webhook] Failed: {url} — {e}")


# Singleton
webhook_service = WebhookService()
