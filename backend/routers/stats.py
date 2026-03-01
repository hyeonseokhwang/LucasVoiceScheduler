"""Statistics API endpoints."""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter

from services.db_service import fetch_one, fetch_all

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
async def stats_summary():
    """Dashboard summary stats for Mobile Commander integration."""
    today = datetime.now().strftime("%Y-%m-%d")

    total_schedules = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status != 'cancelled'"
    ))["cnt"]

    today_schedules = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status = 'active' AND start_at LIKE ?",
        (f"{today}%",),
    ))["cnt"]

    active_challenges = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM challenges WHERE status = 'active'"
    ))["cnt"]

    challenges = await fetch_all("SELECT milestones FROM challenges WHERE status = 'active'")
    completed_milestones = 0
    total_milestones = 0
    for ch in challenges:
        if ch["milestones"]:
            ms_list = json.loads(ch["milestones"]) if isinstance(ch["milestones"], str) else ch["milestones"]
            total_milestones += len(ms_list)
            completed_milestones += sum(1 for m in ms_list if m.get("status") == "completed")

    return {
        "total_schedules": total_schedules,
        "today_schedules": today_schedules,
        "active_challenges": active_challenges,
        "completed_milestones": completed_milestones,
        "total_milestones": total_milestones,
        "date": today,
    }


@router.get("/weekly")
async def stats_weekly():
    """Weekly statistics: schedule completion rate, daily breakdown."""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    ws = week_start.strftime("%Y-%m-%d")
    we = week_end.strftime("%Y-%m-%d")

    # Daily schedule counts for the week
    daily = []
    for i in range(7):
        day = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
        day_label = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]

        total = (await fetch_one(
            "SELECT COUNT(*) as cnt FROM schedules WHERE status != 'cancelled' AND start_at LIKE ?",
            (f"{day}%",),
        ))["cnt"]

        completed = (await fetch_one(
            "SELECT COUNT(*) as cnt FROM schedules WHERE status = 'completed' AND start_at LIKE ?",
            (f"{day}%",),
        ))["cnt"]

        daily.append({
            "date": day,
            "day": day_label,
            "total": total,
            "completed": completed,
        })

    # Week totals
    week_total = sum(d["total"] for d in daily)
    week_completed = sum(d["completed"] for d in daily)
    completion_rate = round(week_completed / week_total * 100, 1) if week_total > 0 else 0

    # Category breakdown
    categories = await fetch_all(
        "SELECT category, COUNT(*) as cnt FROM schedules "
        "WHERE status != 'cancelled' AND start_at >= ? AND start_at <= ? "
        "GROUP BY category ORDER BY cnt DESC",
        (f"{ws}T00:00:00", f"{we}T23:59:59"),
    )

    return {
        "week_start": ws,
        "week_end": we,
        "total": week_total,
        "completed": week_completed,
        "completion_rate": completion_rate,
        "daily": daily,
        "by_category": categories,
    }


@router.get("/monthly")
async def stats_monthly():
    """Monthly statistics: schedule trends, completion rate, busiest days."""
    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")

    # Find last day of month
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    month_end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

    # Total and completed
    total = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status != 'cancelled' "
        "AND start_at >= ? AND start_at <= ?",
        (f"{month_start}T00:00:00", f"{month_end}T23:59:59"),
    ))["cnt"]

    completed = (await fetch_one(
        "SELECT COUNT(*) as cnt FROM schedules WHERE status = 'completed' "
        "AND start_at >= ? AND start_at <= ?",
        (f"{month_start}T00:00:00", f"{month_end}T23:59:59"),
    ))["cnt"]

    completion_rate = round(completed / total * 100, 1) if total > 0 else 0

    # Category breakdown
    categories = await fetch_all(
        "SELECT category, COUNT(*) as cnt FROM schedules "
        "WHERE status != 'cancelled' AND start_at >= ? AND start_at <= ? "
        "GROUP BY category ORDER BY cnt DESC",
        (f"{month_start}T00:00:00", f"{month_end}T23:59:59"),
    )

    # Busiest day of week
    weekday_counts = await fetch_all(
        "SELECT CAST(strftime('%%w', start_at) AS INTEGER) as dow, COUNT(*) as cnt "
        "FROM schedules WHERE status != 'cancelled' "
        "AND start_at >= ? AND start_at <= ? "
        "GROUP BY dow ORDER BY cnt DESC",
        (f"{month_start}T00:00:00", f"{month_end}T23:59:59"),
    )

    dow_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    weekday_stats = [
        {"day": dow_names[r["dow"]], "count": r["cnt"]}
        for r in weekday_counts
    ]

    # Average schedules per day (days elapsed)
    days_elapsed = (today - today.replace(day=1)).days + 1
    avg_per_day = round(total / days_elapsed, 1) if days_elapsed > 0 else 0

    return {
        "month": today.strftime("%Y-%m"),
        "total": total,
        "completed": completed,
        "completion_rate": completion_rate,
        "avg_per_day": avg_per_day,
        "by_category": categories,
        "by_weekday": weekday_stats,
    }
