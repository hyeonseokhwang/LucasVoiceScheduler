import json
from datetime import datetime, timedelta
from typing import Optional
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, YEARLY
from dateutil.relativedelta import relativedelta

from services.db_service import fetch_all, fetch_one, execute, execute_returning

FREQ_MAP = {
    "daily": DAILY,
    "weekly": WEEKLY,
    "monthly": MONTHLY,
    "yearly": YEARLY,
}


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")


def _expand_recurrence(schedule: dict, range_start: datetime, range_end: datetime) -> list[dict]:
    """Expand a recurring schedule into individual occurrences within a date range."""
    rec = json.loads(schedule["recurrence"])
    freq = FREQ_MAP.get(rec.get("freq", "").lower())
    if freq is None:
        return [schedule]

    interval = rec.get("interval", 1)
    until = _parse_dt(rec["until"]) if rec.get("until") else range_end
    byweekday = rec.get("days")  # 0=MO ... 6=SU

    base_start = _parse_dt(schedule["start_at"])
    duration = None
    if schedule.get("end_at"):
        duration = _parse_dt(schedule["end_at"]) - base_start

    rule = rrule(
        freq=freq,
        interval=interval,
        dtstart=base_start,
        until=min(until, range_end),
        byweekday=byweekday,
    )

    occurrences = []
    for dt in rule:
        if dt < range_start - (duration or timedelta(0)):
            continue
        if dt > range_end:
            break
        occ = dict(schedule)
        occ["start_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if duration:
            occ["end_at"] = (dt + duration).strftime("%Y-%m-%dT%H:%M:%S")
        occ["_occurrence_date"] = dt.strftime("%Y-%m-%d")
        occ["_is_occurrence"] = True
        occurrences.append(occ)

    return occurrences


async def list_schedules(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
):
    conditions = ["s.status != 'cancelled'"]
    params = []

    if status:
        conditions.append("s.status = ?")
        params.append(status)
    if category:
        conditions.append("s.category = ?")
        params.append(category)

    # Non-recurring schedules in date range
    date_cond = ""
    if from_date:
        date_cond += " AND s.start_at >= ?"
        params.append(from_date)
    if to_date:
        date_cond += " AND s.start_at <= ?"
        params.append(to_date)

    where = " AND ".join(conditions)
    query = f"""
        SELECT s.* FROM schedules s
        WHERE {where} AND s.recurrence IS NULL {date_cond}
        ORDER BY s.start_at ASC
    """
    non_recurring = await fetch_all(query, tuple(params))

    # Recurring schedules — fetch all, expand in range
    rec_params = []
    rec_conditions = ["s.status != 'cancelled'", "s.recurrence IS NOT NULL", "s.parent_id IS NULL"]
    if status:
        rec_conditions.append("s.status = ?")
        rec_params.append(status)
    if category:
        rec_conditions.append("s.category = ?")
        rec_params.append(category)

    rec_where = " AND ".join(rec_conditions)
    rec_query = f"SELECT s.* FROM schedules s WHERE {rec_where}"
    recurring = await fetch_all(rec_query, tuple(rec_params))

    expanded = []
    if recurring and from_date and to_date:
        range_start = _parse_dt(from_date)
        range_end = _parse_dt(to_date)
        # Get exceptions for this range
        exceptions = await fetch_all(
            "SELECT * FROM schedules WHERE parent_id IS NOT NULL AND start_at >= ? AND start_at <= ?",
            (from_date, to_date),
        )
        exception_keys = {(e["parent_id"], e["start_at"][:10]) for e in exceptions}

        for rec_schedule in recurring:
            occs = _expand_recurrence(rec_schedule, range_start, range_end)
            for occ in occs:
                occ_date = occ.get("_occurrence_date", occ["start_at"][:10])
                if (rec_schedule["id"], occ_date) not in exception_keys:
                    expanded.append(occ)
        expanded.extend(exceptions)

    result = non_recurring + expanded
    result.sort(key=lambda x: x["start_at"])
    return result


async def get_schedule(schedule_id: int):
    return await fetch_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))


async def create_schedule(data: dict) -> dict:
    recurrence = data.get("recurrence")
    if recurrence and isinstance(recurrence, dict):
        recurrence = json.dumps(recurrence)

    # Auto-set remind_at to 10 minutes before start if not specified
    remind_at = data.get("remind_at")
    if not remind_at and not data.get("all_day"):
        try:
            start_dt = _parse_dt(data["start_at"])
            remind_dt = start_dt - timedelta(minutes=10)
            remind_at = remind_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

    row_id = await execute(
        """INSERT INTO schedules (title, description, start_at, end_at, all_day, category, remind_at, recurrence, parent_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["title"],
            data.get("description"),
            data["start_at"],
            data.get("end_at"),
            1 if data.get("all_day") else 0,
            data.get("category", "general"),
            remind_at,
            recurrence,
            data.get("parent_id"),
        ),
    )
    return await fetch_one("SELECT * FROM schedules WHERE id = ?", (row_id,))


async def update_schedule(schedule_id: int, data: dict) -> Optional[dict]:
    existing = await get_schedule(schedule_id)
    if not existing:
        return None

    recurrence = data.get("recurrence", existing["recurrence"])
    if recurrence and isinstance(recurrence, dict):
        recurrence = json.dumps(recurrence)

    await execute(
        """UPDATE schedules SET title=?, description=?, start_at=?, end_at=?, all_day=?,
           category=?, remind_at=?, recurrence=?, status=?
           WHERE id=?""",
        (
            data.get("title", existing["title"]),
            data.get("description", existing["description"]),
            data.get("start_at", existing["start_at"]),
            data.get("end_at", existing["end_at"]),
            1 if data.get("all_day", existing["all_day"]) else 0,
            data.get("category", existing["category"]),
            data.get("remind_at", existing["remind_at"]),
            recurrence,
            data.get("status", existing["status"]),
            schedule_id,
        ),
    )
    return await fetch_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))


async def delete_schedule(schedule_id: int) -> bool:
    """Soft delete — set status to cancelled."""
    _, rowcount = await execute_returning(
        "UPDATE schedules SET status = 'cancelled' WHERE id = ?", (schedule_id,)
    )
    return rowcount > 0


async def complete_schedule(schedule_id: int) -> Optional[dict]:
    await execute("UPDATE schedules SET status = 'completed' WHERE id = ?", (schedule_id,))
    return await fetch_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))


async def get_upcoming(hours: int = 24):
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    until = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    return await list_schedules(from_date=now, to_date=until, status="active")


async def get_calendar_month(year: int, month: int):
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    from_date = f"{year}-{month:02d}-01T00:00:00"
    to_date = f"{year}-{month:02d}-{last_day:02d}T23:59:59"
    return await list_schedules(from_date=from_date, to_date=to_date)


async def search_schedules(query: str, limit: int = 20):
    """Search schedules by title or description."""
    like = f"%{query}%"
    return await fetch_all(
        """SELECT * FROM schedules
           WHERE status != 'cancelled'
           AND (title LIKE ? OR description LIKE ?)
           ORDER BY start_at DESC LIMIT ?""",
        (like, like, limit),
    )


async def get_due_reminders():
    """Get schedules whose remind_at is due (within last 60 seconds)."""
    now = datetime.now()
    window_start = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S")
    window_end = now.strftime("%Y-%m-%dT%H:%M:%S")
    return await fetch_all(
        """SELECT * FROM schedules
           WHERE remind_at IS NOT NULL AND remind_at >= ? AND remind_at <= ?
           AND status = 'active'""",
        (window_start, window_end),
    )
