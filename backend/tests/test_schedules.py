"""Tests for schedule CRUD endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_schedule(client):
    data = {
        "title": "Test Meeting",
        "start_at": "2026-03-10T10:00:00",
        "end_at": "2026-03-10T11:00:00",
        "category": "meeting",
    }
    resp = await client.post("/api/schedules", json=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Test Meeting"
    assert body["category"] == "meeting"
    assert body["status"] == "active"
    assert body["remind_at"] is not None  # auto-set


@pytest.mark.asyncio
async def test_create_schedule_auto_remind(client):
    """remind_at should be auto-set to start_at - 10 minutes."""
    data = {
        "title": "Auto Remind Test",
        "start_at": "2026-03-10T14:00:00",
    }
    resp = await client.post("/api/schedules", json=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["remind_at"] == "2026-03-10T13:50:00"


@pytest.mark.asyncio
async def test_list_schedules(client):
    # Create two schedules
    await client.post("/api/schedules", json={
        "title": "Schedule A",
        "start_at": "2026-03-10T09:00:00",
    })
    await client.post("/api/schedules", json={
        "title": "Schedule B",
        "start_at": "2026-03-10T10:00:00",
    })
    resp = await client.get("/api/schedules", params={
        "from": "2026-03-10T00:00:00",
        "to": "2026-03-10T23:59:59",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_get_schedule(client):
    create_resp = await client.post("/api/schedules", json={
        "title": "Get Test",
        "start_at": "2026-03-11T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.get(f"/api/schedules/{sid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get Test"


@pytest.mark.asyncio
async def test_update_schedule(client):
    create_resp = await client.post("/api/schedules", json={
        "title": "Original",
        "start_at": "2026-03-12T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.put(f"/api/schedules/{sid}", json={
        "title": "Updated Title",
    })
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_delete_schedule(client):
    create_resp = await client.post("/api/schedules", json={
        "title": "To Delete",
        "start_at": "2026-03-13T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.delete(f"/api/schedules/{sid}")
    assert resp.status_code == 200

    # Verify soft-deleted
    get_resp = await client.get(f"/api/schedules/{sid}")
    assert get_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_complete_schedule(client):
    create_resp = await client.post("/api/schedules", json={
        "title": "To Complete",
        "start_at": "2026-03-14T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.post(f"/api/schedules/{sid}/complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_upcoming(client):
    resp = await client.get("/api/schedules/upcoming")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_calendar(client):
    resp = await client.get("/api/schedules/calendar/2026/3")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_search(client):
    await client.post("/api/schedules", json={
        "title": "Unique Search Term XYZ",
        "start_at": "2026-03-15T09:00:00",
    })
    resp = await client.get("/api/schedules/search", params={"q": "XYZ"})
    assert resp.status_code == 200
    data = resp.json()
    assert any("XYZ" in s["title"] for s in data)


@pytest.mark.asyncio
async def test_stats_summary(client):
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_schedules" in body
    assert "active_challenges" in body
    assert "date" in body
