"""
일일 브리핑 자동 생성 서비스
매일 KST 08:00에 오늘 일정을 요약하는 자연어 브리핑을 생성하고 DB에 저장.
고도화: 날씨, 전날 완료 태스크, 우선순위 정렬, 챌린지 D-day.
"""

import asyncio
import json as json_mod
import logging
from datetime import datetime, timedelta, timezone

import httpx

from services.db_service import fetch_all, fetch_one, execute

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"

# 서울 날씨 (OpenWeatherMap free tier)
# API 키가 없으면 하드코딩 fallback 사용
WEATHER_API_KEY = ""  # 비어있으면 하드코딩 사용
WEATHER_CITY = "Seoul"


async def _get_today_schedules(date_str: str) -> list[dict]:
    """Get all active schedules for a given date, sorted by start time."""
    from_dt = f"{date_str}T00:00:00"
    to_dt = f"{date_str}T23:59:59"
    return await fetch_all(
        "SELECT * FROM schedules WHERE status = 'active' "
        "AND start_at >= ? AND start_at <= ? ORDER BY start_at",
        (from_dt, to_dt),
    )


async def _get_yesterday_completed(date_str: str) -> list[dict]:
    """Get schedules completed yesterday."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        yesterday = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return []
    from_dt = f"{yesterday}T00:00:00"
    to_dt = f"{yesterday}T23:59:59"
    return await fetch_all(
        "SELECT * FROM schedules WHERE status = 'completed' "
        "AND start_at >= ? AND start_at <= ? ORDER BY start_at",
        (from_dt, to_dt),
    )


async def _get_active_challenges() -> list[dict]:
    """Get active challenges for briefing context."""
    return await fetch_all(
        "SELECT * FROM challenges WHERE status = 'active'"
    )


async def _get_upcoming_deadlines(date_str: str, days: int = 7) -> list[dict]:
    """Get schedules with deadlines in the next N days."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        end = (dt + timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return []
    return await fetch_all(
        "SELECT * FROM schedules WHERE status = 'active' "
        "AND start_at >= ? AND start_at <= ? ORDER BY start_at",
        (f"{date_str}T00:00:00", f"{end}T23:59:59"),
    )


async def _fetch_weather() -> dict | None:
    """Fetch weather from OpenWeatherMap or return hardcoded seasonal data."""
    if WEATHER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": WEATHER_CITY,
                        "appid": WEATHER_API_KEY,
                        "units": "metric",
                        "lang": "kr",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "temp": round(data["main"]["temp"]),
                        "desc": data["weather"][0]["description"],
                        "humidity": data["main"]["humidity"],
                    }
        except Exception:
            pass

    # Hardcoded seasonal weather for Seoul (March)
    now = datetime.now(KST)
    month = now.month
    if month in (3, 4):
        return {"temp": 8, "desc": "맑음", "humidity": 45, "note": "봄"}
    elif month in (5, 6):
        return {"temp": 22, "desc": "구름 조금", "humidity": 55, "note": "초여름"}
    elif month in (7, 8):
        return {"temp": 30, "desc": "흐림", "humidity": 75, "note": "여름"}
    elif month in (9, 10):
        return {"temp": 18, "desc": "맑음", "humidity": 50, "note": "가을"}
    else:
        return {"temp": -2, "desc": "맑음", "humidity": 40, "note": "겨울"}


def _sort_by_priority(schedules: list[dict]) -> list[dict]:
    """Sort schedules: meetings first, then work, then personal."""
    priority_order = {"meeting": 0, "work": 1, "general": 2, "personal": 3}
    return sorted(
        schedules,
        key=lambda s: (
            priority_order.get(s.get("category", "general"), 2),
            s.get("start_at", ""),
        ),
    )


async def generate_briefing(date_str: str | None = None) -> dict:
    """Generate a daily briefing for the given date (default: today KST)."""
    if date_str is None:
        date_str = datetime.now(KST).strftime("%Y-%m-%d")

    # Check if briefing already exists
    existing = await fetch_one(
        "SELECT * FROM briefings WHERE date = ?", (date_str,)
    )
    if existing:
        return existing

    # Gather all data
    schedules = await _get_today_schedules(date_str)
    yesterday_done = await _get_yesterday_completed(date_str)
    challenges = await _get_active_challenges()
    weather = await _fetch_weather()

    # Build LLM prompt with enriched data
    prompt = _build_llm_prompt(date_str, schedules, yesterday_done, challenges, weather)

    # Generate with LLM
    content = await _call_llm(prompt)
    if not content:
        # Fallback: enhanced template-based briefing
        content = _fallback_briefing(date_str, schedules, yesterday_done, challenges, weather)

    # Save to DB
    await execute(
        "INSERT OR REPLACE INTO briefings (date, content, schedule_count) VALUES (?, ?, ?)",
        (date_str, content, len(schedules)),
    )

    return {
        "date": date_str,
        "content": content,
        "schedule_count": len(schedules),
    }


def _build_llm_prompt(
    date_str: str,
    schedules: list[dict],
    yesterday_done: list[dict],
    challenges: list[dict],
    weather: dict | None,
) -> str:
    """Build enriched LLM prompt."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
        date_display = f"{dt.year}년 {dt.month}월 {dt.day}일 ({weekday})"
    except Exception:
        date_display = date_str

    parts = [f"오늘은 {date_display}입니다.\n"]

    # Weather
    if weather:
        parts.append(f"날씨: {weather['desc']}, {weather['temp']}°C, 습도 {weather['humidity']}%\n")

    # Yesterday completed
    if yesterday_done:
        parts.append(f"\n어제 완료한 일정 ({len(yesterday_done)}건):")
        for s in yesterday_done[:5]:
            parts.append(f"  - {s['title']}")

    # Today schedules (priority sorted)
    if schedules:
        sorted_sched = _sort_by_priority(schedules)
        parts.append(f"\n오늘 일정 ({len(schedules)}건, 우선순위순):")
        for s in sorted_sched:
            cat = s.get("category", "general")
            try:
                t = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
                time_str = t.strftime("%H:%M")
            except Exception:
                time_str = "?"
            parts.append(f"  - {time_str} [{cat}] {s['title']}")
    else:
        parts.append("\n오늘 등록된 일정 없음.")

    # Challenges with D-day
    if challenges:
        parts.append("\n챌린지 현황:")
        for ch in challenges:
            try:
                dl = datetime.strptime(ch["deadline"][:10], "%Y-%m-%d")
                today = datetime.strptime(date_str, "%Y-%m-%d")
                d_day = (dl - today).days
                d_day_str = f"D-{d_day}" if d_day > 0 else "D-DAY" if d_day == 0 else f"D+{abs(d_day)}"
            except Exception:
                d_day_str = "?"
            progress = 0
            if ch["target_amount"] > 0:
                progress = int(ch["current_amount"] / ch["target_amount"] * 100)
            if ch["target_amount"] > 0:
                parts.append(f"  - {ch['title']} ({d_day_str}) {progress}% ({ch['current_amount']:,}원/{ch['target_amount']:,}원)")
            else:
                parts.append(f"  - {ch['title']} ({d_day_str})")
            # Upcoming milestones
            milestones = json_mod.loads(ch["milestones"]) if ch.get("milestones") else []
            for ms in milestones:
                if ms.get("status") == "pending":
                    parts.append(f"    → 다음 마일스톤: {ms['title']} (기한: {ms.get('due_date', '?')})")
                    break

    parts.append("\n위 정보를 바탕으로 오늘의 브리핑을 작성해주세요. "
                 "자연스러운 한국어로, 5-8문장. 인사말로 시작하고, "
                 "날씨→일정 요약→우선 처리 사항→챌린지 현황 순으로 구성.")

    return "\n".join(parts)


async def _call_llm(prompt: str) -> str | None:
    """Call Ollama LLM for briefing generation."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "60m",
                    "options": {"temperature": 0.7, "num_predict": 400},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip() or None
    except Exception as e:
        logger.warning(f"LLM briefing generation failed: {e}")
        return None


def _fallback_briefing(
    date_str: str,
    schedules: list[dict],
    yesterday_done: list[dict],
    challenges: list[dict],
    weather: dict | None,
) -> str:
    """Enhanced template-based fallback when LLM is unavailable."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
        date_display = f"{dt.month}월 {dt.day}일 ({weekday})"
    except Exception:
        date_display = date_str

    sections = []

    # 1. 인사 + 날씨
    greeting = f"좋은 아침입니다! 오늘은 {date_display}입니다."
    if weather:
        greeting += f" 서울 날씨: {weather['desc']} {weather['temp']}°C."
    sections.append(greeting)

    # 2. 어제 완료 요약
    if yesterday_done:
        done_titles = ", ".join(s["title"] for s in yesterday_done[:3])
        suffix = f" 외 {len(yesterday_done) - 3}건" if len(yesterday_done) > 3 else ""
        sections.append(f"[어제 완료] {done_titles}{suffix} — 수고하셨습니다!")

    # 3. 오늘 일정 (우선순위 정렬)
    if schedules:
        sorted_sched = _sort_by_priority(schedules)
        sections.append(f"[오늘 일정] {len(schedules)}건:")

        for s in sorted_sched:
            cat = s.get("category", "general")
            cat_emoji = {"meeting": "[회의]", "work": "[업무]", "personal": "[개인]"}.get(cat, "[일반]")
            try:
                t = datetime.strptime(s["start_at"][:16], "%Y-%m-%dT%H:%M")
                time_str = t.strftime("%H:%M")
            except Exception:
                time_str = "  "
            sections.append(f"  {time_str} {cat_emoji} {s['title']}")

        # Priority call-out
        meetings = [s for s in sorted_sched if s.get("category") == "meeting"]
        if meetings:
            first_meeting = meetings[0]
            try:
                t = datetime.strptime(first_meeting["start_at"][:16], "%Y-%m-%dT%H:%M")
                sections.append(f"→ 첫 미팅 {t.strftime('%H:%M')} '{first_meeting['title']}' 준비하세요.")
            except Exception:
                pass
    else:
        sections.append("[오늘 일정] 등록된 일정이 없습니다. 여유롭게 중요한 프로젝트에 집중하세요!")

    # 4. 챌린지 D-day
    if challenges:
        sections.append("[챌린지 현황]")
        for ch in challenges:
            try:
                dl = datetime.strptime(ch["deadline"][:10], "%Y-%m-%d")
                today = datetime.strptime(date_str, "%Y-%m-%d")
                d_day = (dl - today).days
                if d_day > 0:
                    d_day_str = f"D-{d_day}"
                elif d_day == 0:
                    d_day_str = "D-DAY!"
                else:
                    d_day_str = f"D+{abs(d_day)} 초과"
            except Exception:
                d_day_str = ""

            progress = ""
            if ch["target_amount"] > 0:
                pct = int(ch["current_amount"] / ch["target_amount"] * 100)
                progress = f" {pct}% ({ch['current_amount']:,}원/{ch['target_amount']:,}원)"

            sections.append(f"  {ch['title']} [{d_day_str}]{progress}")

            # Next pending milestone
            milestones = json_mod.loads(ch["milestones"]) if ch.get("milestones") else []
            for ms in milestones:
                if ms.get("status") == "pending":
                    ms_date = ms.get("due_date", "")[:10]
                    try:
                        ms_dl = datetime.strptime(ms_date, "%Y-%m-%d")
                        ms_days = (ms_dl - datetime.strptime(date_str, "%Y-%m-%d")).days
                        ms_dday = f"D-{ms_days}" if ms_days > 0 else "오늘!" if ms_days == 0 else f"D+{abs(ms_days)}"
                    except Exception:
                        ms_dday = ""
                    sections.append(f"    → 다음: {ms['title']} ({ms_dday})")
                    break

    return "\n".join(sections)


class BriefingScheduler:
    """Daily briefing auto-generation at KST 08:00."""

    def __init__(self):
        self._task: asyncio.Task | None = None

    async def _loop(self):
        while True:
            try:
                now = datetime.now(KST)
                # Calculate next 08:00 KST
                target = now.replace(hour=8, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info(
                    f"[Briefing] Next briefing at {target.isoformat()}, "
                    f"waiting {wait_seconds:.0f}s"
                )
                await asyncio.sleep(wait_seconds)

                # Generate today's briefing
                today = datetime.now(KST).strftime("%Y-%m-%d")
                result = await generate_briefing(today)
                logger.info(
                    f"[Briefing] Generated for {today}: "
                    f"{len(result.get('content', ''))} chars, "
                    f"{result.get('schedule_count', 0)} schedules"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Briefing] Error: {e}")
                await asyncio.sleep(60)

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None


briefing_scheduler = BriefingScheduler()
