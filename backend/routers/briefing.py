"""일일 브리핑 API 라우터."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
from services.briefing_service import generate_briefing, get_briefing_config, update_briefing_config
from services.db_service import fetch_one, fetch_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])

KST = timezone(timedelta(hours=9))
TTS_VOICE = "ko-KR-SunHiNeural"
TTS_DIR = Path(__file__).resolve().parent.parent / "tts_cache"


class BriefingConfigUpdate(BaseModel):
    weather: bool | None = None
    yesterday_completed: bool | None = None
    today_schedules: bool | None = None
    challenges: bool | None = None
    priority_sort: bool | None = None
    greeting: bool | None = None


@router.get("/config")
async def get_config():
    """Get current briefing configuration."""
    return get_briefing_config()


@router.put("/config")
async def set_config(body: BriefingConfigUpdate):
    """Update briefing configuration (which sections to include)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return update_briefing_config(updates)


@router.get("/today")
async def get_today_briefing():
    """오늘의 브리핑을 반환. 없으면 즉시 생성."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    result = await generate_briefing(today)
    return result


@router.get("/today/voice")
async def get_today_briefing_voice():
    """오늘의 브리핑을 Edge TTS로 변환하여 MP3로 반환."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    briefing = await generate_briefing(today)
    content = briefing.get("content", "")
    if not content:
        raise HTTPException(404, "No briefing content available")

    TTS_DIR.mkdir(exist_ok=True)
    audio_path = TTS_DIR / f"briefing_{today}.mp3"

    # Generate if not cached
    if not audio_path.exists():
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "edge_tts",
                "--voice", TTS_VOICE,
                "--text", content,
                "--write-media", str(audio_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
            logger.info(f"[TTS] Briefing audio generated: {audio_path} ({audio_path.stat().st_size} bytes)")
        except Exception as e:
            logger.warning(f"[TTS] Briefing generation failed: {e}")
            raise HTTPException(500, f"TTS generation failed: {e}")

    if not audio_path.exists():
        raise HTTPException(500, "TTS file was not created")

    return StreamingResponse(
        open(audio_path, "rb"),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename=briefing_{today}.mp3"},
    )


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
