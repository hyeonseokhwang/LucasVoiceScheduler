"""Schedule conflict detection service."""

from datetime import datetime, timedelta

from services import schedule_service


async def detect_conflicts(
    start_at: str,
    end_at: str | None = None,
    exclude_id: int | None = None,
) -> list[dict]:
    """Detect scheduling conflicts for a given time range.

    Args:
        start_at: ISO datetime string for start
        end_at: ISO datetime string for end (defaults to start + 1 hour)
        exclude_id: Schedule ID to exclude from conflict check (for updates)

    Returns:
        List of conflicting schedule dicts with overlap details.
    """
    try:
        start = datetime.strptime(start_at[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return []

    if end_at:
        try:
            end = datetime.strptime(end_at[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            end = start + timedelta(hours=1)
    else:
        end = start + timedelta(hours=1)

    # Fetch all schedules for the day
    day_start = start.strftime("%Y-%m-%dT00:00:00")
    day_end = start.strftime("%Y-%m-%dT23:59:59")
    day_schedules = await schedule_service.list_schedules(
        from_date=day_start, to_date=day_end, status="active"
    )

    conflicts = []
    for s in day_schedules:
        if exclude_id and s.get("id") == exclude_id:
            continue
        if s.get("all_day"):
            continue

        try:
            s_start = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
            s_end_str = s.get("end_at")
            s_end = (
                datetime.strptime(s_end_str[:16], "%Y-%m-%dT%H:%M")
                if s_end_str
                else s_start + timedelta(hours=1)
            )
        except (ValueError, TypeError):
            continue

        # Check overlap: two ranges overlap if start1 < end2 AND start2 < end1
        if s_start < end and start < s_end:
            # Calculate overlap duration
            overlap_start = max(s_start, start)
            overlap_end = min(s_end, end)
            overlap_minutes = int((overlap_end - overlap_start).total_seconds() / 60)

            conflict = dict(s)
            conflict["_overlap_minutes"] = overlap_minutes
            conflict["_overlap_start"] = overlap_start.strftime("%H:%M")
            conflict["_overlap_end"] = overlap_end.strftime("%H:%M")
            conflicts.append(conflict)

    return conflicts
