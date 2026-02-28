"""
대화형 음성비서 서비스
멀티턴 대화 컨텍스트 관리 + 자연스러운 한국어 응답 생성
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5-coder:7b"
TIMEOUT = 60.0
KEEP_ALIVE = "30m"  # 모델 VRAM 상주 시간 (콜드 로딩 13초 방지)

SYSTEM_PROMPT = """너는 "루카스"라는 이름의 한국어 일정 관리 음성비서야.

역할:
- 사용자의 자연어 일정 요청을 이해하고 친근하게 응답
- 일정 생성, 수정, 삭제, 조회를 도움
- 충돌하는 일정이 있으면 알려주고 대안을 제시
- 확인이 필요하면 짧게 물어봄

응답 규칙:
- 반말로 대화 (친근한 톤, 예: "~할게", "~할까?", "~했어")
- 1-2문장으로 짧고 간결하게
- 이모지 사용 금지
- 시간은 "오후 3시", "내일 아침" 등 자연스러운 한국어로
- 일정 확인 시 반드시 날짜와 시간을 명시

현재 날짜/시간: {now}

액션 태그 (응답 맨 끝에 JSON으로):
- 일정 생성 확인: [ACTION:CREATE]{{json}}
- 일정 수정: [ACTION:MODIFY]{{json}}
- 추가 정보 필요: [ACTION:ASK]
- 단순 대화: [ACTION:NONE]
"""


async def chat_with_context(
    user_text: str,
    history: list[dict],
    parsed_schedule: dict | None = None,
    context_schedules: list[dict] | None = None,
    reference_date: datetime | None = None,
) -> dict:
    """
    Multi-turn conversation with LLM.

    Returns:
        {
            "response": str,       # 자연어 응답
            "action": str,         # CREATE, MODIFY, ASK, NONE
            "schedule_data": dict, # 파싱된 일정 (action이 CREATE/MODIFY일 때)
        }
    """
    now = reference_date or datetime.now()
    system = SYSTEM_PROMPT.format(now=now.strftime("%Y년 %m월 %d일 %A %H:%M"))

    # Build context about existing schedules
    if context_schedules:
        items = []
        for s in context_schedules[:8]:
            t = s.get("start_at", "")[:16]
            items.append(f"- {t} {s.get('title', '?')}")
        system += "\n\n현재 등록된 일정:\n" + "\n".join(items)

    # Build parsed schedule context
    if parsed_schedule and parsed_schedule.get("title"):
        system += (
            f"\n\n사용자 입력에서 파싱된 정보: "
            f"제목='{parsed_schedule.get('title')}', "
            f"시작={parsed_schedule.get('start_at')}, "
            f"종료={parsed_schedule.get('end_at')}, "
            f"카테고리={parsed_schedule.get('category')}"
        )

    # Build message list
    messages = [{"role": "system", "content": system}]

    # Add history (last 10 turns)
    for msg in history[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Add current user message
    messages.append({"role": "user", "content": user_text})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 200,
                    },
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("message", {}).get("content", "").strip()

            if not response_text:
                return _fallback_response(user_text, parsed_schedule)

            # Parse action from response
            action, schedule_data, clean_response = _parse_action(response_text, parsed_schedule)

            return {
                "response": clean_response,
                "action": action,
                "schedule_data": schedule_data,
            }

    except httpx.TimeoutException:
        logger.warning("Ollama chat timed out")
        return _fallback_response(user_text, parsed_schedule, history)
    except httpx.ConnectError:
        logger.warning("Cannot connect to Ollama")
        return _fallback_response(user_text, parsed_schedule, history)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return _fallback_response(user_text, parsed_schedule, history)


async def stream_chat(
    user_text: str,
    history: list[dict],
    parsed_schedule: dict | None = None,
    context_schedules: list[dict] | None = None,
    reference_date: datetime | None = None,
):
    """
    Streaming version of chat - yields response chunks.
    """
    now = reference_date or datetime.now()
    system = SYSTEM_PROMPT.format(now=now.strftime("%Y년 %m월 %d일 %A %H:%M"))

    if context_schedules:
        items = [f"- {s.get('start_at', '')[:16]} {s.get('title', '?')}" for s in context_schedules[:8]]
        system += "\n\n현재 등록된 일정:\n" + "\n".join(items)

    if parsed_schedule and parsed_schedule.get("title"):
        system += (
            f"\n\n파싱된 정보: 제목='{parsed_schedule.get('title')}', "
            f"시작={parsed_schedule.get('start_at')}, 카테고리={parsed_schedule.get('category')}"
        )

    messages = [{"role": "system", "content": system}]
    for msg in history[-10:]:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": True,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"temperature": 0.7, "num_predict": 200},
                },
                timeout=TIMEOUT,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        logger.error(f"Stream chat error: {e}")
        yield _fallback_response(user_text, parsed_schedule).get("response", "")


def _parse_action(response: str, parsed_schedule: dict | None) -> tuple[str, dict | None, str]:
    """Extract action tag from LLM response."""
    import re

    action = "NONE"
    schedule_data = parsed_schedule
    clean = response

    # Look for [ACTION:XXX]{json} pattern
    m = re.search(r"\[ACTION:(\w+)\](\{.*\})?", response, re.DOTALL)
    if m:
        action = m.group(1)
        if m.group(2):
            try:
                schedule_data = json.loads(m.group(2))
            except json.JSONDecodeError:
                pass
        clean = response[:m.start()].strip()

    # If no explicit action but parsed schedule has data, assume CREATE confirmation
    if action == "NONE" and parsed_schedule and parsed_schedule.get("title"):
        # Check if response seems like a confirmation question
        if any(kw in clean for kw in ["생성할", "만들", "잡을", "등록할", "추가할", "할까"]):
            action = "CREATE"

    if not clean:
        clean = response.split("[ACTION")[0].strip() if "[ACTION" in response else response

    return action, schedule_data, clean


def _fallback_response(user_text: str, parsed_schedule: dict | None, history: list[dict] | None = None) -> dict:
    """Template fallback when LLM is unavailable. Context-aware."""
    text_lower = user_text.strip().lower()

    # Check for confirmation patterns
    confirm_words = ["응", "어", "그래", "좋아", "네", "해줘", "해", "확인", "ㅇㅇ", "ㅇ", "ok", "yes"]
    cancel_words = ["아니", "취소", "안해", "말어", "됐어", "ㄴㄴ"]

    if any(text_lower.startswith(w) or text_lower == w for w in confirm_words):
        # Look for pending schedule in history
        if history:
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    # Previous assistant had a CREATE action
                    return {
                        "response": "알겠어, 생성할게!",
                        "action": "CREATE",
                        "schedule_data": parsed_schedule,
                    }
        return {
            "response": "알겠어!",
            "action": "CREATE",
            "schedule_data": parsed_schedule,
        }

    if any(text_lower.startswith(w) or text_lower == w for w in cancel_words):
        return {
            "response": "알겠어, 취소했어.",
            "action": "NONE",
            "schedule_data": None,
        }

    if not parsed_schedule or not parsed_schedule.get("title"):
        return {
            "response": "무슨 일정을 만들까? 날짜랑 시간을 알려줘.",
            "action": "ASK",
            "schedule_data": None,
        }

    title = parsed_schedule.get("title", "새 일정")
    start = parsed_schedule.get("start_at", "")
    try:
        dt = datetime.strptime(start[:16], "%Y-%m-%dT%H:%M")
        if dt.minute == 0:
            time_str = f"{dt.hour}시"
        else:
            time_str = f"{dt.hour}시 {dt.minute}분"

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        target = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        diff = (target - today).days

        if diff == 0:
            date_str = "오늘"
        elif diff == 1:
            date_str = "내일"
        elif diff == 2:
            date_str = "모레"
        else:
            date_str = f"{dt.month}월 {dt.day}일"
    except Exception:
        date_str = start[:10]
        time_str = ""

    return {
        "response": f"{date_str} {time_str}에 '{title}' 잡을까?",
        "action": "CREATE",
        "schedule_data": parsed_schedule,
    }
