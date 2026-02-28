"""
Ollama LLM 연동 서비스
로컬에서 동작하는 Qwen2.5-7B를 활용해 복잡한 자연어를 파싱.
룰 기반 파서의 confidence가 낮을 때만 호출.
"""

import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5-coder:7b"
TIMEOUT = 15.0  # seconds
KEEP_ALIVE = "30m"


async def check_ollama_available() -> bool:
    """Check if Ollama server is running."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False


async def parse_with_llm(
    text: str,
    context_schedules: list[dict] | None = None,
    reference_date: datetime | None = None,
) -> Optional[dict]:
    """
    Use Ollama + Qwen2.5-7B to parse natural language into schedule data.
    """
    now = reference_date or datetime.now()
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    context_str = ""
    if context_schedules:
        items = []
        for s in context_schedules[:10]:
            time_str = s.get("start_at", "")
            end_str = s.get("end_at", "")
            items.append(f"- {s.get('title', '?')} ({time_str} ~ {end_str})")
        context_str = "\n기존 일정:\n" + "\n".join(items)

    prompt = (
        f"현재 날짜/시간: {now.strftime('%Y년 %m월 %d일 %A %H:%M')}\n\n"
        f'사용자 입력: "{text}"\n'
        f"{context_str}\n\n"
        "위 내용을 일정 정보 JSON으로 추출하세요. JSON만 출력하세요.\n\n"
        '{"title": "제목", "start_at": "YYYY-MM-DDTHH:MM", "end_at": "YYYY-MM-DDTHH:MM", '
        '"all_day": false, "category": "general|work|personal|meeting", "description": "", "recurrence": null}\n\n'
        f"참고: 내일={tomorrow}, 시간 미지정시 09:00, 종료 미지정시 시작+1시간"
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 256,
                    },
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "")

            parsed = _extract_json(response_text)
            if parsed:
                return parsed

            logger.warning(f"LLM returned non-JSON response: {response_text[:200]}")
            return None

    except httpx.TimeoutException:
        logger.warning("Ollama request timed out")
        return None
    except httpx.ConnectError:
        logger.warning("Cannot connect to Ollama (is it running?)")
        return None
    except Exception as e:
        logger.error(f"LLM parse error: {e}")
        return None


async def generate_response(
    user_text: str,
    parsed_schedule: dict,
    conflicts: list[dict] | None = None,
    reference_date: datetime | None = None,
) -> str:
    """
    Generate a natural language response about the parsed schedule.
    Falls back to template response if LLM is unavailable.
    """
    now = reference_date or datetime.now()

    title = parsed_schedule.get("title", "새 일정")
    start = parsed_schedule.get("start_at", "")

    try:
        dt = datetime.strptime(start[:16], "%Y-%m-%dT%H:%M")
        date_str = dt.strftime("%m월 %d일")
        if dt.minute == 0:
            time_str = f"{dt.hour}시"
        else:
            time_str = f"{dt.hour}시 {dt.minute}분"
    except Exception:
        date_str = start
        time_str = ""

    if conflicts:
        conflict_titles = ", ".join(f"'{c.get('title', '?')}'" for c in conflicts[:3])
        fallback = f"{date_str} {time_str}에 {conflict_titles}이(가) 있습니다. '{title}'을(를) 그래도 생성할까요?"
    else:
        fallback = f"{date_str} {time_str}에 '{title}' 일정을 생성할까요?"

    # Try LLM for more natural response
    try:
        conflict_str = ""
        if conflicts:
            items = [f"- {c.get('title', '?')} ({c.get('start_at', '')})" for c in conflicts[:5]]
            conflict_str = "\n충돌하는 기존 일정:\n" + "\n".join(items)

        prompt = (
            f'사용자가 "{user_text}"라고 말했고, 다음 일정으로 파싱되었습니다:\n'
            f"제목: {title}, 시간: {date_str} {time_str}\n"
            f"{conflict_str}\n\n"
            "자연스러운 한국어로 짧게(1-2문장) 응답해주세요. 확인을 구하세요."
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"temperature": 0.7, "num_predict": 100},
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            response = data.get("response", "").strip()
            if response:
                return response
    except Exception:
        pass

    return fallback


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from LLM response text."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find bare JSON object
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None
