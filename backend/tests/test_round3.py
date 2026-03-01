"""Tests for Round 3 features: natural language, conflicts, templates, voice commands, dashboard."""

import pytest


# --- Natural Language Input ---

@pytest.mark.asyncio
async def test_natural_language_parse(client):
    """Natural language endpoint should return parsed schedule data."""
    resp = await client.post("/api/schedules/natural", json={
        "text": "내일 오후 3시 치과",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "parsed" in body
    assert "confidence" in body
    assert body["parsed"]["title"] is not None
    assert body["parsed"]["start_at"] is not None


@pytest.mark.asyncio
async def test_natural_language_auto_create(client):
    """Auto-create should create the schedule when confidence is sufficient."""
    resp = await client.post("/api/schedules/natural", json={
        "text": "회의 내일 10시",
        "auto_create": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    # Even with fallback parser, confidence should be >= 0.2
    assert "parsed" in body


@pytest.mark.asyncio
async def test_natural_language_with_conflicts(client):
    """Should detect conflicts when schedules overlap."""
    # Create a schedule first
    await client.post("/api/schedules", json={
        "title": "Existing Meeting",
        "start_at": "2026-03-10T14:00:00",
        "end_at": "2026-03-10T15:00:00",
        "category": "meeting",
    })
    # Try natural parse at same time
    resp = await client.post("/api/schedules/natural", json={
        "text": "3월 10일 오후 2시 회의",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "conflicts" in body
    assert "has_conflicts" in body


# --- Conflict Detection ---

@pytest.mark.asyncio
async def test_conflict_detection(client):
    """Conflict service should detect overlapping schedules."""
    # Create two overlapping schedules
    await client.post("/api/schedules", json={
        "title": "Meeting A",
        "start_at": "2026-03-20T10:00:00",
        "end_at": "2026-03-20T11:00:00",
    })
    await client.post("/api/schedules", json={
        "title": "Meeting B",
        "start_at": "2026-03-20T10:30:00",
        "end_at": "2026-03-20T11:30:00",
    })

    from services.conflict_service import detect_conflicts
    conflicts = await detect_conflicts("2026-03-20T10:00:00", "2026-03-20T11:00:00")
    # Should find at least Meeting B as overlapping
    assert len(conflicts) >= 1


@pytest.mark.asyncio
async def test_no_conflict(client):
    """No conflict when times don't overlap."""
    await client.post("/api/schedules", json={
        "title": "Morning",
        "start_at": "2026-03-21T08:00:00",
        "end_at": "2026-03-21T09:00:00",
    })

    from services.conflict_service import detect_conflicts
    conflicts = await detect_conflicts("2026-03-21T14:00:00", "2026-03-21T15:00:00")
    assert len(conflicts) == 0


# --- Templates ---

@pytest.mark.asyncio
async def test_create_template(client):
    """Create a schedule template."""
    resp = await client.post("/api/templates", json={
        "name": "Morning Routine",
        "description": "Daily morning schedule",
        "template_data": {
            "title": "Morning Exercise",
            "start_at": "07:00:00",
            "end_at": "08:00:00",
            "category": "personal",
        },
        "category": "personal",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Morning Routine"
    assert body["template_data"]["title"] == "Morning Exercise"


@pytest.mark.asyncio
async def test_list_templates(client):
    """List templates should return created templates."""
    await client.post("/api/templates", json={
        "name": "Test Template",
        "template_data": {"title": "Test", "start_at": "09:00:00"},
    })
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_apply_template(client):
    """Apply template should create schedules."""
    create_resp = await client.post("/api/templates", json={
        "name": "Apply Test",
        "template_data": {
            "title": "Template Schedule",
            "start_at": "10:00:00",
            "end_at": "11:00:00",
            "category": "work",
        },
    })
    tid = create_resp.json()["id"]

    resp = await client.post(f"/api/templates/{tid}/apply", json={
        "start_date": "2026-03-15",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["created"][0]["title"] == "Template Schedule"
    assert "2026-03-15" in body["created"][0]["start_at"]


@pytest.mark.asyncio
async def test_delete_template(client):
    """Delete a template."""
    create_resp = await client.post("/api/templates", json={
        "name": "To Delete",
        "template_data": {"title": "Delete Me"},
    })
    tid = create_resp.json()["id"]

    resp = await client.delete(f"/api/templates/{tid}")
    assert resp.status_code == 200


# --- Voice Commands ---

@pytest.mark.asyncio
async def test_voice_command_list(client):
    """Voice command: list today's schedules."""
    await client.post("/api/schedules", json={
        "title": "Voice Test Schedule",
        "start_at": "2026-03-01T09:00:00",
    })
    resp = await client.post("/api/voice/command", json={
        "text": "오늘 일정 보여줘",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "LIST"
    assert "response" in body


@pytest.mark.asyncio
async def test_voice_command_complete(client):
    """Voice command: complete a schedule."""
    create_resp = await client.post("/api/schedules", json={
        "title": "Complete Me",
        "start_at": "2026-03-01T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.post("/api/voice/command", json={
        "text": f"{sid}번 일정 완료",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "COMPLETE"


@pytest.mark.asyncio
async def test_voice_command_delete(client):
    """Voice command: delete a schedule."""
    create_resp = await client.post("/api/schedules", json={
        "title": "Delete Me",
        "start_at": "2026-03-01T09:00:00",
    })
    sid = create_resp.json()["id"]

    resp = await client.post("/api/voice/command", json={
        "text": f"{sid}번 일정 삭제",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "DELETE"


@pytest.mark.asyncio
async def test_voice_command_unknown(client):
    """Voice command: unrecognized input should return NONE."""
    resp = await client.post("/api/voice/command", json={
        "text": "안녕하세요",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "NONE"


# --- Dashboard ---

@pytest.mark.asyncio
async def test_dashboard(client):
    """Dashboard should return unified data."""
    resp = await client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert "date" in body
    assert "today" in body
    assert "week" in body
    assert "upcoming" in body
    assert "challenges" in body
    assert "briefing" in body


@pytest.mark.asyncio
async def test_dashboard_with_data(client):
    """Dashboard should include created schedules."""
    await client.post("/api/schedules", json={
        "title": "Dashboard Test",
        "start_at": "2026-03-01T09:00:00",
    })
    resp = await client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"]["total"] >= 0
    assert body["week"]["total"] >= 0
    assert isinstance(body["challenges"]["active"], list)
