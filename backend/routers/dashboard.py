"""Unified dashboard API endpoint."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from services.db_service import fetch_one, fetch_all
from services import schedule_service, challenge_service

router = APIRouter(prefix="/api", tags=["dashboard"])

KST = timezone(timedelta(hours=9))


@router.get("/dashboard")
async def dashboard():
    """Unified dashboard: today's schedules, week summary, challenges, briefing status.

    Returns everything Mobile Commander needs in a single API call.
    """
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    today_start = f"{today}T00:00:00"
    today_end = f"{today}T23:59:59"

    # 1. Today's schedules
    today_schedules = await schedule_service.list_schedules(
        from_date=today_start, to_date=today_end
    )

    # 2. Week summary
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)
    ws = week_start.strftime("%Y-%m-%d")
    we = week_end.strftime("%Y-%m-%d")

    week_total = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status != 'cancelled' "
        "AND start_at >= ? AND start_at <= ?",
        (f"{ws}T00:00:00", f"{we}T23:59:59"),
    ))["cnt"]

    week_completed = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status = 'completed' "
        "AND start_at >= ? AND start_at <= ?",
        (f"{ws}T00:00:00", f"{we}T23:59:59"),
    ))["cnt"]

    week_rate = round(week_completed / week_total * 100, 1) if week_total > 0 else 0

    # 3. Challenges
    challenges = await challenge_service.list_challenges("active")

    # 4. Briefing status
    briefing = await fetch_one(
        "SELECT date, content FROM briefings WHERE date = ? ORDER BY id DESC LIMIT 1",
        (today,),
    )
    briefing_status = {
        "available": briefing is not None,
        "date": today,
        "preview": (briefing["content"][:100] + "...") if briefing and briefing.get("content") else None,
    }

    # 5. Upcoming (next 4 hours)
    upcoming_end = (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S")
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")
    upcoming = await schedule_service.list_schedules(
        from_date=now_str, to_date=upcoming_end, status="active"
    )

    return {
        "date": today,
        "time": now.strftime("%H:%M"),
        "today": {
            "schedules": today_schedules,
            "total": len(today_schedules),
            "completed": sum(1 for s in today_schedules if s.get("status") == "completed"),
            "active": sum(1 for s in today_schedules if s.get("status") == "active"),
        },
        "week": {
            "start": ws,
            "end": we,
            "total": week_total,
            "completed": week_completed,
            "completion_rate": week_rate,
        },
        "upcoming": {
            "schedules": upcoming,
            "count": len(upcoming),
            "next": upcoming[0] if upcoming else None,
        },
        "challenges": {
            "active": challenges,
            "count": len(challenges),
        },
        "briefing": briefing_status,
    }
