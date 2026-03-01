"""Tests for briefing endpoints."""

import pytest


@pytest.mark.asyncio
async def test_get_today_briefing(client):
    resp = await client.get("/api/briefing/today")
    assert resp.status_code == 200
    body = resp.json()
    assert "date" in body
    assert "content" in body
    assert len(body["content"]) > 0


@pytest.mark.asyncio
async def test_get_briefing_by_date(client):
    resp = await client.get("/api/briefing/2026-03-01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-03-01"


@pytest.mark.asyncio
async def test_list_briefings(client):
    # Generate one first
    await client.get("/api/briefing/today")
    resp = await client.get("/api/briefing", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_briefing_caching(client):
    """Second call should return cached briefing."""
    resp1 = await client.get("/api/briefing/2026-03-15")
    resp2 = await client.get("/api/briefing/2026-03-15")
    assert resp1.json()["content"] == resp2.json()["content"]
