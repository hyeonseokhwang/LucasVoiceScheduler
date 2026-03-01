"""일일 브리핑 API 라우터."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from services.briefing_service import generate_briefing
from services.db_service import fetch_one, fetch_all

router = APIRouter(prefix="/api/briefing", tags=["briefing"])

KST = timezone(timedelta(hours=9))


@router.get("/today")
async def get_today_briefing():
    """오늘의 브리핑을 반환. 없으면 즉시 생성."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    result = await generate_briefing(today)
    return result


@router.get("/{date}")
async def get_briefing_by_date(date: str):
    """특정 날짜의 브리핑 조회. 없으면 생성."""
    result = await generate_briefing(date)
    return result


@router.get("")
async def list_briefings(limit: int = Query(default=7, le=30)):
    """최근 브리핑 목록 조회."""
    rows = await fetch_all(
        "SELECT * FROM briefings ORDER BY date DESC LIMIT ?",
        (limit,),
    )
    return rows
