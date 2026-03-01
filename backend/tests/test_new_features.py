"""Tests for new features: recurrence, briefing config, stats, notifications."""

import pytest


# --- Recurrence Engine Tests ---

@pytest.mark.asyncio
async def test_create_recurring_schedule(client):
    """Create a recurring schedule with weekly frequency."""
    data = {
        "title": "Weekly Standup",
        "start_at": "2026-03-02T10:00:00",
        "end_at": "2026-03-02T10:30:00",
        "category": "meeting",
        "recurrence": {
            "freq": "weekly",
            "interval": 1,
            "days": [0],  # Monday
            "until": "2026-04-30",
        },
    }
    resp = await client.post("/api/schedules", json=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Weekly Standup"
    assert body["recurrence"] is not None


@pytest.mark.asyncio
async def test_recurrence_exception_skip(client):
    """Skip a specific date in a recurring schedule."""
    # Create recurring schedule
    create_resp = await client.post("/api/schedules", json={
        "title": "Daily Task",
        "start_at": "2026-03-01T09:00:00",
        "recurrence": {
            "freq": "daily",
            "interval": 1,
            "until": "2026-03-31",
        },
    })
    sid = create_resp.json()["id"]

    # Add skip exception
    resp = await client.post(f"/api/schedules/{sid}/exception", json={
        "date": "2026-03-15",
        "action": "skip",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "skip"
    assert "2026-03-15" in body["exclude_dates"]


@pytest.mark.asyncio
async def test_recurrence_exception_invalid(client):
    """Exception on non-recurring schedule should fail."""
    create_resp = await client.post("/api/schedules", json={
        "title": "Non-recurring",
        "start_at": "2026-03-10T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.post(f"/api/schedules/{sid}/exception", json={
        "date": "2026-03-10",
        "action": "skip",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recurring_expansion_in_list(client):
    """Recurring schedule should expand when listing with date range."""
    await client.post("/api/schedules", json={
        "title": "Daily Expand Test",
        "start_at": "2026-03-01T08:00:00",
        "recurrence": {
            "freq": "daily",
            "interval": 1,
            "until": "2026-03-07",
        },
    })
    resp = await client.get("/api/schedules", params={
        "from_date": "2026-03-01T00:00:00",
        "to_date": "2026-03-07T23:59:59",
    })
    assert resp.status_code == 200
    data = resp.json()
    # Should have multiple occurrences (daily from March 1, until covers range)
    expand_count = sum(1 for s in data if s["title"] == "Daily Expand Test")
    assert expand_count >= 6


# --- Briefing Config Tests ---

@pytest.mark.asyncio
async def test_get_briefing_config(client):
    """Default briefing config should have all sections enabled."""
    resp = await client.get("/api/briefing/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weather"] is True
    assert body["today_schedules"] is True
    assert body["challenges"] is True


@pytest.mark.asyncio
async def test_update_briefing_config(client):
    """Should be able to disable specific briefing sections."""
    resp = await client.put("/api/briefing/config", json={
        "weather": False,
        "greeting": False,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["weather"] is False
    assert body["greeting"] is False
    # Other sections should remain True
    assert body["today_schedules"] is True


# --- Stats API Tests ---

@pytest.mark.asyncio
async def test_stats_weekly(client):
    """Weekly stats should return daily breakdown."""
    # Create some schedules for this week
    await client.post("/api/schedules", json={
        "title": "Week Test A",
        "start_at": "2026-03-02T09:00:00",
        "category": "work",
    })
    resp = await client.get("/api/stats/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert "week_start" in body
    assert "week_end" in body
    assert "daily" in body
    assert len(body["daily"]) == 7
    assert "completion_rate" in body
    # Each daily entry should have date, day, total, completed
    day = body["daily"][0]
    assert "date" in day
    assert "day" in day
    assert "total" in day
    assert "completed" in day


@pytest.mark.asyncio
async def test_stats_monthly(client):
    """Monthly stats should return completion rate and category breakdown."""
    resp = await client.get("/api/stats/monthly")
    assert resp.status_code == 200
    body = resp.json()
    assert "month" in body
    assert "total" in body
    assert "completed" in body
    assert "completion_rate" in body
    assert "avg_per_day" in body
    assert "by_category" in body
    assert "by_weekday" in body


@pytest.mark.asyncio
async def test_stats_summary_fields(client):
    """Stats summary should include milestone counts."""
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_schedules" in body
    assert "today_schedules" in body
    assert "active_challenges" in body
    assert "completed_milestones" in body
    assert "total_milestones" in body
    assert "date" in body


# --- Notification Channel Tests ---

@pytest.mark.asyncio
async def test_notification_manager():
    """NotificationManager should register and dispatch to channels."""
    from services.notification import NotificationManager, LogChannel

    mgr = NotificationManager()
    log_ch = LogChannel()
    mgr.register(log_ch)

    assert "log" in mgr.channels

    results = await mgr.broadcast({"type": "test", "message": "hello"})
    assert results["log"] is True


@pytest.mark.asyncio
async def test_notification_channel_unregister():
    """Unregistered channel should not receive messages."""
    from services.notification import NotificationManager, LogChannel

    mgr = NotificationManager()
    log_ch = LogChannel()
    mgr.register(log_ch)
    mgr.unregister("log")

    assert "log" not in mgr.channels


@pytest.mark.asyncio
async def test_websocket_channel_not_available():
    """WebSocketChannel with no connections should not be available."""
    from services.notification import WebSocketChannel

    ch = WebSocketChannel()
    assert await ch.is_available() is False
    result = await ch.send({"type": "test"})
    assert result is False
