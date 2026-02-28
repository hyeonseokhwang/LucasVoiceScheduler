from typing import Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services import schedule_service
from services.reminder_service import reminder_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_at: str
    end_at: Optional[str] = None
    all_day: bool = False
    category: str = "general"
    remind_at: Optional[str] = None
    recurrence: Optional[dict] = None
    parent_id: Optional[int] = None


class ScheduleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    all_day: Optional[bool] = None
    category: Optional[str] = None
    remind_at: Optional[str] = None
    recurrence: Optional[dict] = None
    status: Optional[str] = None


@router.get("")
async def list_schedules(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    return await schedule_service.list_schedules(from_date, to_date, status, category)


@router.get("/search")
async def search_schedules(q: str = Query(..., min_length=1)):
    return await schedule_service.search_schedules(q)


@router.get("/upcoming")
async def upcoming(hours: int = Query(24)):
    return await schedule_service.get_upcoming(hours)


@router.get("/calendar/{year}/{month}")
async def calendar_month(year: int, month: int):
    if month < 1 or month > 12:
        raise HTTPException(400, "Month must be 1-12")
    return await schedule_service.get_calendar_month(year, month)


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: int):
    result = await schedule_service.get_schedule(schedule_id)
    if not result:
        raise HTTPException(404, "Schedule not found")
    return result


@router.post("")
async def create_schedule(body: ScheduleCreate):
    return await schedule_service.create_schedule(body.model_dump())


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: int, body: ScheduleUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await schedule_service.update_schedule(schedule_id, data)
    if not result:
        raise HTTPException(404, "Schedule not found")
    return result


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int):
    ok = await schedule_service.delete_schedule(schedule_id)
    if not ok:
        raise HTTPException(404, "Schedule not found")
    return {"ok": True}


@router.post("/{schedule_id}/complete")
async def complete_schedule(schedule_id: int):
    result = await schedule_service.complete_schedule(schedule_id)
    if not result:
        raise HTTPException(404, "Schedule not found")
    return result


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await reminder_service.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        reminder_service.disconnect(ws)
