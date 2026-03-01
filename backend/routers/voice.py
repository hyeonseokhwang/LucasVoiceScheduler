"""
음성비서 API 라우터
POST /api/voice/parse      — 텍스트 → 일정 파싱 + 충돌 검사 + 응답 생성
POST /api/voice/confirm    — 파싱된 일정 확정 생성
POST /api/voice/chat       — 대화형 음성비서 (멀티턴, 자연스러운 응답)
POST /api/voice/transcribe — 음성 → 텍스트 (로컬 Whisper STT)
POST /api/voice/tts        — 텍스트 → 음성 (Edge TTS, Neural 음성)
GET  /api/voice/context    — 특정 날짜 주변 일정 컨텍스트 조회
GET  /api/voice/status     — 서비스 상태 확인
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import schedule_service
from services.nlp_service import parse_korean_datetime
from services.llm_service import parse_with_llm, generate_response, check_ollama_available
from services.conversation_service import chat_with_context, stream_chat
from services import whisper_service

router = APIRouter(prefix="/api/voice", tags=["voice"])

LLM_THRESHOLD = 0.4


class VoiceParseRequest(BaseModel):
    text: str


class VoiceConfirmRequest(BaseModel):
    title: str
    start_at: str
    end_at: Optional[str] = None
    all_day: bool = False
    category: str = "general"
    description: Optional[str] = None
    remind_at: Optional[str] = None
    recurrence: Optional[dict] = None


class VoiceChatRequest(BaseModel):
    text: str
    history: list[dict] = []
    stream: bool = False


@router.post("/parse")
async def voice_parse(body: VoiceParseRequest):
    """
    Parse natural language text into schedule data.
    1. Rule-based Korean parser (fast, free)
    2. If low confidence → Ollama LLM (local, free)
    3. Check for conflicts with existing schedules
    4. Generate natural language response
    """
    text = body.text.strip()
    if not text:
        return {"error": "텍스트가 비어있습니다", "parsed": None, "confidence": 0}

    now = datetime.now()

    # Step 1: Rule-based parsing
    parsed = parse_korean_datetime(text, reference=now)
    confidence = parsed.get("confidence", 0)

    # Step 2: If low confidence, try LLM
    if confidence < LLM_THRESHOLD:
        start_date = parsed.get("start_at", now.strftime("%Y-%m-%dT%H:%M"))
        context = await _get_nearby_schedules(start_date)

        llm_result = await parse_with_llm(text, context_schedules=context, reference_date=now)
        if llm_result:
            for key in ["title", "start_at", "end_at", "all_day", "category", "description", "recurrence"]:
                if key in llm_result and llm_result[key] is not None:
                    parsed[key] = llm_result[key]
            confidence = max(confidence + 0.3, 0.6)
            parsed["confidence"] = confidence

    # Step 3: Check for conflicts
    conflicts = await _check_conflicts(parsed.get("start_at", ""), parsed.get("end_at"))

    # Step 4: Generate response
    response_text = await generate_response(
        user_text=text, parsed_schedule=parsed, conflicts=conflicts, reference_date=now,
    )

    return {
        "parsed": {
            "title": parsed.get("title", "새 일정"),
            "start_at": parsed.get("start_at", ""),
            "end_at": parsed.get("end_at"),
            "all_day": parsed.get("all_day", False),
            "category": parsed.get("category", "general"),
            "description": parsed.get("description"),
            "recurrence": parsed.get("recurrence"),
        },
        "confidence": confidence,
        "response": response_text,
        "conflicts": conflicts,
    }


@router.post("/chat")
async def voice_chat(body: VoiceChatRequest):
    """
    대화형 음성비서.
    멀티턴 대화로 자연스러운 일정 관리.
    history를 통해 맥락 유지.
    """
    text = body.text.strip()
    if not text:
        return {"response": "뭐라고 했어? 다시 말해줘.", "action": "ASK", "schedule_data": None}

    now = datetime.now()

    # Step 1: Rule-based parsing
    parsed = parse_korean_datetime(text, reference=now)
    confidence = parsed.get("confidence", 0)

    # Get context schedules
    start_date = parsed.get("start_at", now.strftime("%Y-%m-%dT%H:%M"))
    context = await _get_nearby_schedules(start_date)

    # Step 2: Check for conflicts
    conflicts = []
    if confidence > 0.2:
        conflicts = await _check_conflicts(parsed.get("start_at", ""), parsed.get("end_at"))

    # Step 3: Chat with LLM (always use LLM for natural response)
    # Enrich parsed data with conflict info
    if conflicts:
        conflict_info = [{"title": c.get("title"), "start_at": c.get("start_at")} for c in conflicts[:3]]
        parsed["_conflicts"] = conflict_info

    chat_result = await chat_with_context(
        user_text=text,
        history=body.history,
        parsed_schedule=parsed if confidence > 0.15 else None,
        context_schedules=context,
        reference_date=now,
    )

    # Merge schedule data from chat result with parsed data
    schedule_data = chat_result.get("schedule_data") or parsed
    if schedule_data and "_conflicts" in schedule_data:
        del schedule_data["_conflicts"]
    if schedule_data and "confidence" in schedule_data:
        del schedule_data["confidence"]

    return {
        "response": chat_result.get("response", ""),
        "action": chat_result.get("action", "NONE"),
        "schedule_data": schedule_data,
        "confidence": confidence,
        "conflicts": conflicts,
    }


@router.post("/chat/stream")
async def voice_chat_stream(body: VoiceChatRequest):
    """
    스트리밍 대화 응답. Server-Sent Events로 실시간 응답.
    """
    text = body.text.strip()
    now = datetime.now()

    parsed = parse_korean_datetime(text, reference=now)
    confidence = parsed.get("confidence", 0)
    start_date = parsed.get("start_at", now.strftime("%Y-%m-%dT%H:%M"))
    context = await _get_nearby_schedules(start_date)

    async def generate():
        async for chunk in stream_chat(
            user_text=text,
            history=body.history,
            parsed_schedule=parsed if confidence > 0.15 else None,
            context_schedules=context,
            reference_date=now,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    """
    로컬 Whisper STT — 음성 파일을 텍스트로 변환.
    완전 로컬, GPU 가속 (RTX 4090 기준 1-2초 이내).
    WebM, WAV, MP3 등 지원.
    """
    if not whisper_service.is_available():
        return {"text": "", "error": "Whisper not installed"}

    audio_bytes = await audio.read()
    if not audio_bytes:
        return {"text": "", "error": "Empty audio"}

    result = await whisper_service.transcribe_audio(audio_bytes, language="ko")
    return result


@router.post("/confirm")
async def voice_confirm(body: VoiceConfirmRequest):
    """Create a schedule from confirmed voice parsing result."""
    data = body.model_dump()
    result = await schedule_service.create_schedule(data)
    return result


@router.get("/context")
async def voice_context(date: str = Query(...)):
    """Get schedules around a specific date for context."""
    try:
        target = datetime.strptime(date[:10], "%Y-%m-%d")
    except ValueError:
        target = datetime.now()

    from_date = (target - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    to_date = (target + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59")

    schedules = await schedule_service.list_schedules(from_date=from_date, to_date=to_date)

    if not schedules:
        summary = f"{target.strftime('%m월 %d일')} 전후로 일정이 없습니다."
    else:
        items = []
        for s in schedules[:10]:
            try:
                dt = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = ""
            items.append(f"{time_str} {s.get('title', '?')}")
        summary = f"{target.strftime('%m월 %d일')} 전후 일정:\n" + "\n".join(items)

    return {"schedules": schedules, "summary": summary}


class TTSRequest(BaseModel):
    text: str
    voice: str = "ko-KR-SunHiNeural"
    rate: str = "+10%"


def _sanitize_for_tts(text: str) -> str:
    """TTS 전에 에러코드, 디버그 텍스트, 액션 태그 등을 제거."""
    import re

    # 1. [ACTION:XXX] + 선택적 JSON (중첩 포함) 패턴 제거
    #    예: [ACTION:CREATE]{"title":"회의","start_at":"..."}
    #    예: [ACTION:NONE], [ACTION:ASK]
    text = re.sub(r'\[ACTION:\w+\]\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})?', '', text)

    # 2. 코드 블록 제거
    text = re.sub(r'```[\s\S]*?```', '', text)

    # 3. JSON 객체 제거 ({"key": "value"} 형태)
    text = re.sub(r'\{[^{}]*"[^"]*"\s*:[^{}]*\}', '', text)

    # 4. 에러/디버그 문자열 제거
    error_patterns = [
        r'\bUNDEFINED\b', r'\bUNPARSED\s*TEXT\b', r'\bundefined\b',
        r'\bnull\b', r'\bNaN\b', r'\bERROR\b', r'\bError\b',
        r'directive within the instructions provided',
        r'as an AI language model',
        r'I cannot|I\'m sorry.*I can\'t',
    ]
    for pat in error_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # 5. 잔여 대괄호 태그 제거 — [대문자_:대문자_] 패턴 전체
    text = re.sub(r'\[[A-Z_]+(?::[A-Z_]+)*\]', '', text)

    # 6. 연속 공백 정리
    text = re.sub(r'\s+', ' ', text).strip()

    return text


@router.post("/tts")
async def voice_tts(body: TTSRequest):
    """Edge TTS — 텍스트를 자연스러운 Neural 음성(MP3)으로 변환."""
    import edge_tts

    text = _sanitize_for_tts(body.text.strip())
    if not text:
        return {"error": "텍스트가 비어있습니다"}

    async def generate():
        comm = edge_tts.Communicate(text, body.voice, rate=body.rate)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(generate(), media_type="audio/mpeg")


@router.get("/status")
async def voice_status():
    """Check voice service status."""
    ollama_ok = await check_ollama_available()
    whisper_status = whisper_service.get_status()
    return {
        "nlp_parser": True,
        "ollama": ollama_ok,
        "model": "qwen2.5-coder:7b" if ollama_ok else None,
        "whisper": whisper_status,
        "features": {
            "conversation": ollama_ok,
            "streaming": ollama_ok,
            "tts": True,
            "tts_engine": "edge-tts",
            "stt_local": whisper_status["available"],
            "stt_browser": True,
        },
    }


async def _get_nearby_schedules(start_at: str) -> list[dict]:
    try:
        target = datetime.strptime(start_at[:10], "%Y-%m-%d")
    except ValueError:
        target = datetime.now()

    from_date = target.strftime("%Y-%m-%dT00:00:00")
    to_date = target.strftime("%Y-%m-%dT23:59:59")
    return await schedule_service.list_schedules(from_date=from_date, to_date=to_date)


async def _check_conflicts(start_at: str, end_at: str | None) -> list[dict]:
    if not start_at:
        return []

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

    day_start = start.strftime("%Y-%m-%dT00:00:00")
    day_end = start.strftime("%Y-%m-%dT23:59:59")
    day_schedules = await schedule_service.list_schedules(from_date=day_start, to_date=day_end)

    conflicts = []
    for s in day_schedules:
        try:
            s_start = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
            s_end_str = s.get("end_at")
            s_end = datetime.strptime(s_end_str[:16], "%Y-%m-%dT%H:%M") if s_end_str else s_start + timedelta(hours=1)
            if s_start < end and s_end > start:
                conflicts.append(s)
        except (ValueError, TypeError):
            continue

    return conflicts
