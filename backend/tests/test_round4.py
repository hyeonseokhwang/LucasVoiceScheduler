"""Tests for Round 4: Telegram, iCal, webhooks, health check, Docker readiness."""

import pytest


# --- Telegram Channel ---

@pytest.mark.asyncio
async def test_telegram_channel_unavailable():
    """Telegram channel should be unavailable without env vars."""
    from services.telegram_channel import TelegramChannel
    ch = TelegramChannel(token="", chat_id="")
    assert await ch.is_available() is False


@pytest.mark.asyncio
async def test_telegram_channel_name():
    """Telegram channel name should be 'telegram'."""
    from services.telegram_channel import TelegramChannel
    ch = TelegramChannel()
    assert ch.name == "telegram"


@pytest.mark.asyncio
async def test_telegram_message_formatting():
    """Telegram should format messages with HTML."""
    from services.telegram_channel import TelegramChannel
    ch = TelegramChannel()
    msg = ch._format_message({"type": "reminder", "message": "Test", "schedule": {"category": "work"}})
    assert "<b>" in msg
    assert "Test" in msg


# --- iCal Export ---

@pytest.mark.asyncio
async def test_ical_export(client):
    """iCal export should return valid .ics content."""
    await client.post("/api/schedules", json={
        "title": "iCal Test",
        "start_at": "2026-03-15T10:00:00",
        "end_at": "2026-03-15T11:00:00",
        "category": "meeting",
    })
    resp = await client.get("/api/schedules/export/ical", params={
        "from_date": "2026-03-01T00:00:00",
        "to_date": "2026-03-31T23:59:59",
    })
    assert resp.status_code == 200
    content = resp.text
    assert "BEGIN:VCALENDAR" in content
    assert "BEGIN:VEVENT" in content
    assert "iCal Test" in content
    assert "END:VCALENDAR" in content


@pytest.mark.asyncio
async def test_ical_export_empty(client):
    """iCal export with no matching schedules should return empty calendar."""
    resp = await client.get("/api/schedules/export/ical", params={
        "from_date": "2099-01-01T00:00:00",
        "to_date": "2099-01-31T23:59:59",
    })
    assert resp.status_code == 200
    content = resp.text
    assert "BEGIN:VCALENDAR" in content
    assert "VEVENT" not in content or content.count("VEVENT") == 0


@pytest.mark.asyncio
async def test_ical_content_type(client):
    """iCal export should have text/calendar content type."""
    resp = await client.get("/api/schedules/export/ical")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers.get("content-type", "")


# --- Webhook Service ---

@pytest.mark.asyncio
async def test_webhook_service_add_remove():
    """Webhook service should add and remove URLs."""
    from services.webhook_service import WebhookService
    ws = WebhookService()
    ws.add_url("http://example.com/hook")
    assert "http://example.com/hook" in ws.urls
    ws.remove_url("http://example.com/hook")
    assert "http://example.com/hook" not in ws.urls


@pytest.mark.asyncio
async def test_webhook_dispatch_no_urls():
    """Webhook dispatch with no URLs should not error."""
    from services.webhook_service import WebhookService
    ws = WebhookService()
    # Should complete without error
    await ws.dispatch("test.event", {"key": "value"})


@pytest.mark.asyncio
async def test_webhook_integrated_in_create(client):
    """Schedule creation should trigger webhook (no error even without URLs)."""
    resp = await client.post("/api/schedules", json={
        "title": "Webhook Test",
        "start_at": "2026-03-20T10:00:00",
    })
    assert resp.status_code == 200
    assert resp.json()["title"] == "Webhook Test"


# --- Enhanced Health Check ---

@pytest.mark.asyncio
async def test_health_check_enhanced(client):
    """Enhanced health check should return component statuses."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert "db" in body["checks"]
    assert "tts" in body["checks"]
    assert "ollama" in body["checks"]
    assert "websocket" in body["checks"]
    assert "notifications" in body["checks"]


@pytest.mark.asyncio
async def test_health_db_ok(client):
    """DB should be ok in test environment."""
    resp = await client.get("/api/health")
    body = resp.json()
    assert body["checks"]["db"]["status"] == "ok"
