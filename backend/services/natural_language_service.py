"""Natural language schedule input service.

Parses free-form Korean text into structured schedule data using Ollama LLM.
Examples:
  '매주 월요일 오전 9시 스탠드업' → weekly recurring at 09:00
  '내일 오후 3시 치과' → one-time tomorrow at 15:00
  '다음주 금요일 저녁 7시 회식' → one-time next Friday at 19:00
"""

import json
import logging
import re
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"
TIMEOUT = 30.0
KEEP_ALIVE = "60m"

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _http_client


async def parse_natural_language(text: str) -> dict:
    """Parse natural language text into schedule data using LLM.

    Returns a dict with:
      - schedule: parsed schedule fields (title, start_at, end_at, category, recurrence, etc.)
      - confidence: float 0-1
      - raw_response: LLM response text
    """
    now = datetime.now()
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    today_weekday = weekday_names[now.weekday()]

    prompt = f"""현재: {now.strftime('%Y-%m-%d %H:%M')} ({today_weekday})

사용자 입력: "{text}"

이 입력을 일정 정보 JSON으로 변환하세요. 다음 형식을 따르세요:

{{
  "title": "일정 제목",
  "start_at": "YYYY-MM-DDTHH:MM:SS",
  "end_at": "YYYY-MM-DDTHH:MM:SS",
  "all_day": false,
  "category": "general|work|personal|meeting",
  "description": "설명 (없으면 null)",
  "recurrence": null
}}

반복 일정인 경우 recurrence:
{{
  "freq": "daily|weekly|monthly|yearly",
  "interval": 1,
  "days": [0],
  "until": "YYYY-MM-DD"
}}

규칙:
- "매주"/"매일"/"매월" → recurrence 설정. until은 3개월 후.
- 요일: 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
- 시간 미지정 → 09:00
- 종료 미지정 → 시작+1시간
- "회의"/"미팅"/"스탠드업" → category: "meeting"
- "운동"/"헬스"/"조깅" → category: "personal"
- JSON만 출력하세요. 설명 없이."""

    try:
        client = _get_client()
        resp = await client.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {"temperature": 0.1, "num_predict": 300},
            },
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        parsed = _extract_json(raw)

        if parsed:
            # Validate and fix fields
            schedule = _validate_schedule(parsed, now)
            return {"schedule": schedule, "confidence": 0.85, "raw_response": raw}

        logger.warning(f"[NaturalLang] LLM non-JSON response: {raw[:200]}")
        return {"schedule": _fallback_parse(text, now), "confidence": 0.3, "raw_response": raw}

    except httpx.ConnectError:
        logger.warning("[NaturalLang] Ollama not available, using fallback parser")
        return {"schedule": _fallback_parse(text, now), "confidence": 0.3, "raw_response": ""}
    except httpx.TimeoutException:
        logger.warning("[NaturalLang] Ollama timeout, using fallback parser")
        return {"schedule": _fallback_parse(text, now), "confidence": 0.3, "raw_response": ""}
    except Exception as e:
        logger.error(f"[NaturalLang] Error: {e}")
        return {"schedule": _fallback_parse(text, now), "confidence": 0.2, "raw_response": ""}


def _validate_schedule(data: dict, now: datetime) -> dict:
    """Validate and fix parsed schedule data."""
    schedule = {
        "title": data.get("title", "새 일정"),
        "start_at": data.get("start_at", ""),
        "end_at": data.get("end_at"),
        "all_day": data.get("all_day", False),
        "category": data.get("category", "general"),
        "description": data.get("description"),
        "recurrence": data.get("recurrence"),
    }

    # Validate category
    if schedule["category"] not in ("general", "work", "personal", "meeting"):
        schedule["category"] = "general"

    # Validate start_at
    if not schedule["start_at"]:
        schedule["start_at"] = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    # Validate end_at
    if not schedule["end_at"] and not schedule["all_day"]:
        try:
            start = datetime.strptime(schedule["start_at"][:16], "%Y-%m-%dT%H:%M")
            schedule["end_at"] = (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass

    # Validate recurrence
    if schedule["recurrence"]:
        rec = schedule["recurrence"]
        if isinstance(rec, dict):
            if rec.get("freq") not in ("daily", "weekly", "monthly", "yearly"):
                schedule["recurrence"] = None
            elif not rec.get("until"):
                # Default until: 3 months from now
                rec["until"] = (now + timedelta(days=90)).strftime("%Y-%m-%d")

    return schedule


def _fallback_parse(text: str, now: datetime) -> dict:
    """Simple rule-based fallback when LLM is unavailable."""
    title = text
    start = now + timedelta(hours=1)
    category = "general"

    # Detect category keywords
    if any(k in text for k in ("회의", "미팅", "스탠드업", "standup")):
        category = "meeting"
    elif any(k in text for k in ("운동", "헬스", "조깅", "러닝")):
        category = "personal"
    elif any(k in text for k in ("업무", "작업", "코딩", "개발")):
        category = "work"

    # Detect time patterns
    time_match = re.search(r'(\d{1,2})[시:](\d{0,2})', text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if "오후" in text or "저녁" in text:
            if hour < 12:
                hour += 12
        start = start.replace(hour=hour, minute=minute)

    # Detect "내일"
    if "내일" in text:
        start = (now + timedelta(days=1)).replace(hour=start.hour, minute=start.minute)

    return {
        "title": title,
        "start_at": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_at": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "all_day": False,
        "category": category,
        "description": None,
        "recurrence": None,
    }


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None
