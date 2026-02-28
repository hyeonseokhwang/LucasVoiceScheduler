"""
한국어 자연어 → 일정 데이터 파서 (룰 기반 1차 파싱)
Ollama 없이도 동작하는 기본 파서. v2
"""

import re
from datetime import datetime, timedelta

# 요일 매핑 (0=월 ... 6=일)
DAY_MAP = {
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3,
    "금요일": 4, "토요일": 5, "일요일": 6,
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
}

# 시간 표현 매핑
TIME_KEYWORDS = {
    "새벽": 5, "아침": 8, "오전": 9, "낮": 12,
    "점심": 12, "오후": 14, "저녁": 18, "밤": 21,
}

# 카테고리 키워드 매핑
CATEGORY_KEYWORDS = {
    "회의": "meeting", "미팅": "meeting", "면접": "meeting", "인터뷰": "meeting",
    "업무": "work", "작업": "work", "프로젝트": "work", "개발": "work",
    "운동": "personal", "병원": "personal", "약속": "personal", "데이트": "personal",
}

# 반복 키워드
RECURRENCE_MAP = {
    "매일": {"freq": "daily", "interval": 1},
    "매주": {"freq": "weekly", "interval": 1},
    "매월": {"freq": "monthly", "interval": 1},
    "매년": {"freq": "yearly", "interval": 1},
    "평일마다": {"freq": "weekly", "interval": 1, "days": [0, 1, 2, 3, 4]},
    "주말마다": {"freq": "weekly", "interval": 1, "days": [5, 6]},
}


def parse_korean_datetime(text: str, reference: datetime | None = None) -> dict:
    """
    한국어 자연어 텍스트를 일정 데이터로 파싱.

    Returns:
        {
            "title": str,
            "start_at": str (ISO),
            "end_at": str (ISO) | None,
            "all_day": bool,
            "category": str,
            "recurrence": dict | None,
            "confidence": float (0.0 ~ 1.0),
        }
    """
    now = reference or datetime.now()
    original_text = text.strip()
    remaining = original_text
    confidence = 0.0

    parsed_date: datetime | None = None
    parsed_time: int | None = None  # hour
    parsed_minute: int = 0
    duration_minutes: int = 60
    all_day = False
    category = "general"
    recurrence = None

    # ── 1. 반복 패턴 감지 ──
    for keyword, rec_data in RECURRENCE_MAP.items():
        if keyword in remaining:
            recurrence = rec_data
            remaining = remaining.replace(keyword, "").strip()
            confidence += 0.15
            break

    # ── 2. 날짜 파싱 ──

    # "내일", "모레", "오늘"
    if "내일" in remaining:
        parsed_date = now + timedelta(days=1)
        remaining = remaining.replace("내일", "").strip()
        confidence += 0.2
    elif "모레" in remaining:
        parsed_date = now + timedelta(days=2)
        remaining = remaining.replace("모레", "").strip()
        confidence += 0.2
    elif "오늘" in remaining:
        parsed_date = now
        remaining = remaining.replace("오늘", "").strip()
        confidence += 0.2
    elif "글피" in remaining:
        parsed_date = now + timedelta(days=3)
        remaining = remaining.replace("글피", "").strip()
        confidence += 0.2

    # "다음주 X요일" / "이번주 X요일"
    if parsed_date is None:
        m = re.search(r"(다음주|이번주|이번|다음)\s*(월|화|수|목|금|토|일)(?:요일)?", remaining)
        if m:
            prefix = m.group(1)
            day_name = m.group(2)
            target_dow = DAY_MAP.get(day_name, 0)
            current_dow = now.weekday()

            if prefix in ("다음주", "다음"):
                # Next week's target day
                days_ahead = (7 - current_dow) + target_dow
                parsed_date = now + timedelta(days=days_ahead)
            else:
                # This week's target day
                days_ahead = target_dow - current_dow
                if days_ahead <= 0:
                    days_ahead += 7
                parsed_date = now + timedelta(days=days_ahead)

            remaining = remaining[:m.start()] + remaining[m.end():]
            remaining = remaining.strip()
            confidence += 0.2

    # "X월 Y일" or "M/D"
    if parsed_date is None:
        m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", remaining)
        if m:
            mon = int(m.group(1))
            day = int(m.group(2))
            target = now.replace(month=mon, day=day)
            # If the date has passed this year, assume next year
            if target < now - timedelta(days=1):
                target = target.replace(year=target.year + 1)
            parsed_date = target
            remaining = remaining[:m.start()] + remaining[m.end():]
            remaining = remaining.strip()
            confidence += 0.2

    # "X일" (same month)
    if parsed_date is None:
        m = re.search(r"(\d{1,2})일", remaining)
        if m:
            day = int(m.group(1))
            try:
                target = now.replace(day=day)
                if target < now - timedelta(days=1):
                    if now.month == 12:
                        target = target.replace(year=now.year + 1, month=1)
                    else:
                        target = target.replace(month=now.month + 1)
                parsed_date = target
                remaining = remaining[:m.start()] + remaining[m.end():]
                remaining = remaining.strip()
                confidence += 0.15
            except ValueError:
                pass

    # ── 3. 시간 파싱 ──

    # "오후 3시 30분", "오전 10시", "3시 반"
    m = re.search(r"(오전|오후|새벽|아침|낮|저녁|밤)?\s*(\d{1,2})시\s*(?:(\d{1,2})분|반)?", remaining)
    if m:
        period = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else (30 if "반" in (m.group(0) or "") else 0)

        if period == "오후" and hour < 12:
            hour += 12
        elif period == "오전" and hour == 12:
            hour = 0
        elif period in TIME_KEYWORDS and hour < 12:
            base = TIME_KEYWORDS[period]
            if base >= 12 and hour < 12:
                hour += 12

        parsed_time = hour
        parsed_minute = minute
        remaining = remaining[:m.start()] + remaining[m.end():]
        remaining = remaining.strip()
        confidence += 0.2
    else:
        # Check for time keywords alone: "점심", "저녁" etc
        for keyword, hour_val in TIME_KEYWORDS.items():
            if keyword in remaining:
                parsed_time = hour_val
                remaining = remaining.replace(keyword, "", 1).strip()
                confidence += 0.1
                break

    # ── 4. 기간 파싱 ──
    m = re.search(r"(\d+)\s*시간", remaining)
    if m:
        duration_minutes = int(m.group(1)) * 60
        remaining = remaining[:m.start()] + remaining[m.end():]
        remaining = remaining.strip()
        confidence += 0.1

    m = re.search(r"(\d+)\s*분(?:간)?", remaining)
    if m:
        duration_minutes = int(m.group(1))
        remaining = remaining[:m.start()] + remaining[m.end():]
        remaining = remaining.strip()
        confidence += 0.1

    if "반나절" in remaining:
        duration_minutes = 4 * 60
        remaining = remaining.replace("반나절", "").strip()
        confidence += 0.1

    if "종일" in remaining or "하루종일" in remaining:
        all_day = True
        remaining = remaining.replace("하루종일", "").replace("종일", "").strip()
        confidence += 0.1

    # ── 5. 카테고리 감지 ──
    for keyword, cat in CATEGORY_KEYWORDS.items():
        if keyword in remaining:
            category = cat
            confidence += 0.05
            break

    # ── 5.5 요일 단독 등장 시 날짜 파싱 ──
    if parsed_date is None:
        m = re.search(r"(월|화|수|목|금|토|일)요일", remaining)
        if m:
            day_name = m.group(1)
            target_dow = DAY_MAP.get(day_name, 0)
            current_dow = now.weekday()
            days_ahead = target_dow - current_dow
            if days_ahead <= 0:
                days_ahead += 7
            parsed_date = now + timedelta(days=days_ahead)
            remaining = remaining[:m.start()] + remaining[m.end():]
            remaining = remaining.strip()
            confidence += 0.15

    # ── 6. 제목 추출 ──
    # Clean up remaining text for title
    title = remaining.strip()
    # Remove standalone day names that might remain
    title = re.sub(r"\b(월요일|화요일|수요일|목요일|금요일|토요일|일요일)\b", "", title)
    # Remove common filler words
    for filler in ["에", "잡아줘", "잡아", "만들어줘", "만들어", "등록해줘", "등록해",
                    "추가해줘", "추가해", "넣어줘", "넣어", "해줘", "줘", "좀",
                    "일정", "스케줄", "동안"]:
        title = re.sub(rf"\s*{re.escape(filler)}\s*", " ", title)
    title = re.sub(r"\s+", " ", title).strip()

    if not title:
        title = "새 일정"

    # ── 7. 결과 조합 ──

    # Default to tomorrow if no date parsed
    if parsed_date is None:
        parsed_date = now + timedelta(days=1)
        confidence = max(confidence - 0.1, 0)

    # Default time to 9:00 if no time parsed
    if parsed_time is None and not all_day:
        parsed_time = 9
        confidence = max(confidence - 0.05, 0)

    if all_day:
        start_dt = parsed_date.replace(hour=0, minute=0, second=0)
        end_dt = None
    else:
        start_dt = parsed_date.replace(hour=parsed_time or 9, minute=parsed_minute, second=0)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

    confidence = min(confidence, 1.0)

    result = {
        "title": title,
        "start_at": start_dt.strftime("%Y-%m-%dT%H:%M"),
        "end_at": end_dt.strftime("%Y-%m-%dT%H:%M") if end_dt else None,
        "all_day": all_day,
        "category": category,
        "recurrence": recurrence,
        "confidence": round(confidence, 2),
    }

    return result
