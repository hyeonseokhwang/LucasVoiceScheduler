"""Natural language schedule input router."""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from services.natural_language_service import parse_natural_language
from services.conflict_service import detect_conflicts
from services import schedule_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class NaturalInput(BaseModel):
    text: str
    auto_create: bool = False


@router.post("/natural")
async def natural_language_schedule(body: NaturalInput):
    """Parse natural language text into a schedule.

    Examples:
      '매주 월요일 오전 9시 스탠드업'
      '내일 오후 3시 치과'
      '다음주 금요일 저녁 7시 회식'

    If auto_create is True, the schedule is created immediately.
    Otherwise, returns parsed data for user confirmation.
    """
    result = await parse_natural_language(body.text)
    schedule_data = result["schedule"]
    confidence = result["confidence"]

    # Check for conflicts
    conflicts = await detect_conflicts(
        schedule_data.get("start_at", ""),
        schedule_data.get("end_at"),
    )

    response = {
        "parsed": schedule_data,
        "confidence": confidence,
        "conflicts": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "start_at": c.get("start_at"),
                "end_at": c.get("end_at"),
                "overlap_minutes": c.get("_overlap_minutes", 0),
            }
            for c in conflicts
        ],
        "has_conflicts": len(conflicts) > 0,
        "created": None,
    }

    # Auto-create if requested and confidence is high enough
    if body.auto_create and confidence >= 0.5:
        created = await schedule_service.create_schedule(schedule_data)
        response["created"] = created

    return response
