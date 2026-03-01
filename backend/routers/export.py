"""Schedule export router (iCal .ics format)."""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import Response

from services import schedule_service

router = APIRouter(prefix="/api/schedules/export", tags=["export"])


@router.get("/ical")
async def export_ical(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """Export schedules as iCal (.ics) file.

    Compatible with Google Calendar, Apple Calendar, Outlook.
    Defaults to current month if no date range specified.
    """
    now = datetime.now()
    if not from_date:
        from_date = now.replace(day=1).strftime("%Y-%m-%dT00:00:00")
    if not to_date:
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        to_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%dT23:59:59")

    schedules = await schedule_service.list_schedules(
        from_date=from_date, to_date=to_date, category=category,
    )

    ical = _build_ical(schedules)

    return Response(
        content=ical,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=lucas-schedule.ics",
        },
    )


def _build_ical(schedules: list[dict]) -> str:
    """Build iCal (RFC 5545) content from schedule list."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lucas Initiative//Scheduler//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Lucas Scheduler",
        "X-WR-TIMEZONE:Asia/Seoul",
    ]

    for s in schedules:
        lines.append("BEGIN:VEVENT")

        # UID
        sid = s.get("id", 0)
        occ_date = s.get("_occurrence_date", "")
        uid = f"schedule-{sid}"
        if occ_date:
            uid += f"-{occ_date}"
        lines.append(f"UID:{uid}@lucas-scheduler")

        # Timestamps
        start_at = s.get("start_at", "")
        end_at = s.get("end_at", "")

        if s.get("all_day"):
            dt_start = _to_ical_date(start_at)
            lines.append(f"DTSTART;VALUE=DATE:{dt_start}")
            if end_at:
                dt_end = _to_ical_date(end_at)
                lines.append(f"DTEND;VALUE=DATE:{dt_end}")
        else:
            dt_start = _to_ical_datetime(start_at)
            lines.append(f"DTSTART:{dt_start}")
            if end_at:
                dt_end = _to_ical_datetime(end_at)
                lines.append(f"DTEND:{dt_end}")

        # Summary and description
        title = _escape_ical(s.get("title", ""))
        lines.append(f"SUMMARY:{title}")

        desc = s.get("description")
        if desc:
            lines.append(f"DESCRIPTION:{_escape_ical(desc)}")

        # Category
        category = s.get("category", "general")
        lines.append(f"CATEGORIES:{category.upper()}")

        # Status
        status = s.get("status", "active")
        if status == "completed":
            lines.append("STATUS:COMPLETED")
        elif status == "cancelled":
            lines.append("STATUS:CANCELLED")
        else:
            lines.append("STATUS:CONFIRMED")

        # Created timestamp
        lines.append(f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _to_ical_datetime(dt_str: str) -> str:
    """Convert ISO datetime to iCal format (YYYYMMDDTHHMMSS)."""
    try:
        dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y%m%dT%H%M%S")
    except ValueError:
        try:
            dt = datetime.strptime(dt_str[:16], "%Y-%m-%dT%H:%M")
            return dt.strftime("%Y%m%dT%H%M%S")
        except ValueError:
            return dt_str.replace("-", "").replace(":", "").replace("T", "T")[:15]


def _to_ical_date(dt_str: str) -> str:
    """Convert ISO date to iCal date format (YYYYMMDD)."""
    return dt_str[:10].replace("-", "")


def _escape_ical(text: str) -> str:
    """Escape special characters for iCal text."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )
