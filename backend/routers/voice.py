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

from services import schedule_service, challenge_service
from services.nlp_service import parse_korean_datetime
from services.llm_service import parse_with_llm, generate_response, check_ollama_available
from services.conversation_service import chat_with_context, stream_chat
from services import whisper_service
from services.challenge_nlp import parse_challenge_command

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
    0. Check for challenge commands first
    1. Rule-based Korean parser (fast, free)
    2. If low confidence → Ollama LLM (local, free)
    3. Check for conflicts with existing schedules
    4. Generate natural language response
    """
    text = body.text.strip()
    if not text:
        return {"error": "텍스트가 비어있습니다", "parsed": None, "confidence": 0}

    # Step 0: Challenge command detection
    challenge_cmd = parse_challenge_command(text)
    if challenge_cmd:
        result = await _handle_challenge_command(challenge_cmd)
        return {
            "parsed": None,
            "confidence": 1.0,
            "response": result["response"],
            "conflicts": [],
            "challenge_action": result,
        }

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

    # Challenge command detection
    challenge_cmd = parse_challenge_command(text)
    if challenge_cmd:
        result = await _handle_challenge_command(challenge_cmd)
        return {
            "response": result["response"],
            "action": "CHALLENGE",
            "schedule_data": None,
            "confidence": 1.0,
            "conflicts": [],
            "challenge_action": result,
        }

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


class VoiceCommandRequest(BaseModel):
    text: str


@router.post("/command")
async def voice_command(body: VoiceCommandRequest):
    """Process a text command to perform schedule CRUD operations.

    Supports commands like:
      '내일 회의 추가해줘'      → CREATE
      '오늘 일정 보여줘'        → LIST
      '3번 일정 삭제해줘'       → DELETE
      '5번 일정 완료'           → COMPLETE
      '이번주 일정'             → LIST (week)
    """
    text = body.text.strip()
    if not text:
        return {"action": "NONE", "response": "명령이 비어있습니다."}

    # Detect intent
    action, result = await _process_command(text)
    return {"action": action, **result}


async def _process_command(text: str) -> tuple[str, dict]:
    """Parse and execute a voice command."""
    import re

    # DELETE pattern: "N번 일정 삭제"
    m = re.search(r'(\d+)\s*번?\s*일정?\s*(삭제|취소|제거)', text)
    if m:
        sid = int(m.group(1))
        ok = await schedule_service.delete_schedule(sid)
        if ok:
            return "DELETE", {"response": f"{sid}번 일정을 삭제했습니다.", "schedule_id": sid}
        return "DELETE", {"response": f"{sid}번 일정을 찾을 수 없습니다.", "error": True}

    # COMPLETE pattern: "N번 일정 완료"
    m = re.search(r'(\d+)\s*번?\s*일정?\s*(완료|끝|마감)', text)
    if m:
        sid = int(m.group(1))
        result = await schedule_service.complete_schedule(sid)
        if result:
            return "COMPLETE", {"response": f"'{result['title']}' 일정을 완료했습니다.", "schedule": result}
        return "COMPLETE", {"response": f"{sid}번 일정을 찾을 수 없습니다.", "error": True}

    # LIST patterns
    if any(k in text for k in ("일정 보여", "일정 알려", "뭐 있", "스케줄", "일정 목록")):
        if any(k in text for k in ("이번주", "이번 주", "금주")):
            schedules = await schedule_service.get_upcoming(hours=168)
            label = "이번 주"
        elif any(k in text for k in ("내일",)):
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            schedules = await schedule_service.list_schedules(
                from_date=f"{tomorrow}T00:00:00", to_date=f"{tomorrow}T23:59:59"
            )
            label = "내일"
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            schedules = await schedule_service.list_schedules(
                from_date=f"{today}T00:00:00", to_date=f"{today}T23:59:59"
            )
            label = "오늘"

        if not schedules:
            return "LIST", {"response": f"{label} 일정이 없습니다.", "schedules": []}

        items = []
        for s in schedules[:10]:
            try:
                dt = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
                t = dt.strftime("%H:%M")
            except ValueError:
                t = ""
            items.append(f"{t} {s['title']}")

        return "LIST", {
            "response": f"{label} 일정 {len(schedules)}건:\n" + "\n".join(items),
            "schedules": schedules,
        }

    # CREATE pattern: anything that mentions adding/creating
    if any(k in text for k in ("추가", "생성", "만들", "등록", "넣어", "잡아")):
        from services.natural_language_service import parse_natural_language
        from services.conflict_service import detect_conflicts

        result = await parse_natural_language(text)
        schedule_data = result["schedule"]

        conflicts = await detect_conflicts(
            schedule_data.get("start_at", ""),
            schedule_data.get("end_at"),
        )

        if result["confidence"] >= 0.5:
            created = await schedule_service.create_schedule(schedule_data)
            conflict_msg = f" (주의: {len(conflicts)}건 겹침)" if conflicts else ""
            return "CREATE", {
                "response": f"'{created['title']}' 일정을 추가했습니다.{conflict_msg}",
                "schedule": created,
                "conflicts": conflicts,
            }
        else:
            return "CREATE", {
                "response": "일정을 정확히 파악하지 못했습니다. 다시 말씀해주세요.",
                "parsed": schedule_data,
                "confidence": result["confidence"],
            }

    # Fallback: try natural language parse
    return "NONE", {"response": "명령을 이해하지 못했습니다. '일정 추가', '오늘 일정', '3번 삭제' 등으로 말해주세요."}


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


# Available Edge TTS voices
TTS_VOICES = [
    # Korean
    {"id": "ko-KR-SunHiNeural", "name": "선희 (여성)", "lang": "ko", "gender": "female"},
    {"id": "ko-KR-InJoonNeural", "name": "인준 (남성)", "lang": "ko", "gender": "male"},
    {"id": "ko-KR-BongJinNeural", "name": "봉진 (남성)", "lang": "ko", "gender": "male"},
    {"id": "ko-KR-GookMinNeural", "name": "국민 (남성)", "lang": "ko", "gender": "male"},
    {"id": "ko-KR-JiMinNeural", "name": "지민 (여성)", "lang": "ko", "gender": "female"},
    {"id": "ko-KR-SeoHyeonNeural", "name": "서현 (여성)", "lang": "ko", "gender": "female"},
    {"id": "ko-KR-SoonBokNeural", "name": "순복 (여성)", "lang": "ko", "gender": "female"},
    {"id": "ko-KR-YuJinNeural", "name": "유진 (여성)", "lang": "ko", "gender": "female"},
    # English
    {"id": "en-US-GuyNeural", "name": "Guy (Male)", "lang": "en", "gender": "male"},
    {"id": "en-US-JennyNeural", "name": "Jenny (Female)", "lang": "en", "gender": "female"},
    {"id": "en-US-AriaNeural", "name": "Aria (Female)", "lang": "en", "gender": "female"},
    # Japanese
    {"id": "ja-JP-KeitaNeural", "name": "Keita (Male)", "lang": "ja", "gender": "male"},
    {"id": "ja-JP-NanamiNeural", "name": "Nanami (Female)", "lang": "ja", "gender": "female"},
]


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


@router.get("/reminder/{schedule_id}")
async def get_reminder_audio(schedule_id: int):
    """Get TTS audio file for a schedule reminder."""
    from pathlib import Path
    tts_dir = Path(__file__).resolve().parent.parent / "tts_cache"
    audio_path = tts_dir / f"reminder_{schedule_id}.mp3"
    if not audio_path.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "Reminder audio not found")
    return StreamingResponse(
        open(audio_path, "rb"),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename=reminder_{schedule_id}.mp3"},
    )


@router.get("/voices")
async def list_voices(lang: Optional[str] = Query(None)):
    """Available Edge TTS voices. Filter by lang: ko, en, ja."""
    if lang:
        return [v for v in TTS_VOICES if v["lang"] == lang]
    return TTS_VOICES


class VoiceSettingRequest(BaseModel):
    voice: str


@router.put("/settings/voice")
async def set_default_voice(body: VoiceSettingRequest):
    """Set default TTS voice for reminders and briefings."""
    from services.reminder_service import reminder_service
    valid_ids = {v["id"] for v in TTS_VOICES}
    if body.voice not in valid_ids:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown voice: {body.voice}")
    reminder_service.tts_voice = body.voice
    return {"voice": body.voice, "message": "Default voice updated"}


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


async def _handle_challenge_command(cmd: dict) -> dict:
    """챌린지 관련 음성 명령을 처리합니다."""
    command = cmd["command"]

    if command == "STATUS":
        challenges = await challenge_service.list_challenges("active")
        if not challenges:
            return {"command": "STATUS", "response": "진행 중인 챌린지가 없어."}

        parts = []
        for ch in challenges:
            detail = await challenge_service.get_challenge(ch["id"])
            progress = detail["progress"]
            pct = progress["percentage"]
            d_day = progress["d_day"]
            current = detail["current_amount"]
            target = detail["target_amount"]

            d_str = f"D-{d_day}" if d_day > 0 else ("D-Day!" if d_day == 0 else f"D+{abs(d_day)}")

            parts.append(
                f"{detail['title']}: {current:,}원 달성, {pct}% 진행, {d_str}. "
                f"마일스톤 {progress['milestones_done']}/{progress['milestones_total']}개 완료."
            )

            # Upcoming milestones
            milestones = detail.get("milestones") or []
            pending = [m for m in milestones if m.get("status") != "completed"]
            if pending:
                next_ms = pending[0]
                parts.append(f"다음 마일스톤: {next_ms['title']} ({next_ms['due_date'][5:]})")

        return {"command": "STATUS", "response": " ".join(parts), "challenges": challenges}

    elif command == "ADD_EARNING":
        amount = cmd["amount"]
        source = cmd.get("source")
        challenges = await challenge_service.list_challenges("active")
        if not challenges:
            return {"command": "ADD_EARNING", "response": "진행 중인 챌린지가 없어서 수익을 기록할 수 없어."}

        # Add to first active challenge
        ch = challenges[0]
        earning = await challenge_service.add_earning(ch["id"], {
            "amount": amount,
            "source": source,
        })

        detail = await challenge_service.get_challenge(ch["id"])
        pct = detail["progress"]["percentage"]
        remaining = detail["progress"]["remaining"]

        source_str = f" ({source})" if source else ""
        response = f"{amount:,}원{source_str} 수익을 기록했어! 현재 {detail['current_amount']:,}원, {pct}% 달성."
        if remaining > 0:
            response += f" 목표까지 {remaining:,}원 남았어."
        else:
            response += " 목표를 달성했어!"

        return {"command": "ADD_EARNING", "response": response, "earning": earning}

    elif command == "COMPLETE_MILESTONE":
        milestone_name = cmd.get("milestone_name", "")
        challenges = await challenge_service.list_challenges("active")
        if not challenges:
            return {"command": "COMPLETE_MILESTONE", "response": "진행 중인 챌린지가 없어."}

        # Search for matching milestone
        for ch in challenges:
            detail = await challenge_service.get_challenge(ch["id"])
            milestones = detail.get("milestones") or []
            for i, ms in enumerate(milestones):
                if ms.get("status") == "completed":
                    continue
                # Fuzzy match: check if milestone_name is contained in title or vice versa
                if (milestone_name and (
                    milestone_name in ms["title"] or
                    ms["title"] in milestone_name or
                    _fuzzy_match(milestone_name, ms["title"])
                )):
                    await challenge_service.update_milestone(ch["id"], i, "completed")
                    return {
                        "command": "COMPLETE_MILESTONE",
                        "response": f"'{ms['title']}' 마일스톤을 완료 처리했어!",
                    }

            # If no name specified, complete the next pending milestone
            if not milestone_name:
                for i, ms in enumerate(milestones):
                    if ms.get("status") != "completed":
                        await challenge_service.update_milestone(ch["id"], i, "completed")
                        return {
                            "command": "COMPLETE_MILESTONE",
                            "response": f"'{ms['title']}' 마일스톤을 완료 처리했어!",
                        }

        return {"command": "COMPLETE_MILESTONE", "response": "일치하는 마일스톤을 찾지 못했어."}

    return {"command": command, "response": "알 수 없는 챌린지 명령이야."}


def _fuzzy_match(a: str, b: str) -> bool:
    """간단한 유사도 매칭 (공통 글자 비율)."""
    a_set = set(a.replace(" ", ""))
    b_set = set(b.replace(" ", ""))
    if not a_set or not b_set:
        return False
    overlap = len(a_set & b_set)
    return overlap / min(len(a_set), len(b_set)) > 0.5


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
