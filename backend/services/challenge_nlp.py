"""
챌린지 관련 음성 명령 파서 (룰 기반)
- '챌린지 현황' → 현재 챌린지 상태 조회
- '수익 등록 5000원 앱스토어' → 수익 기록 추가
- '마일스톤 완료 MVP 출시' → 마일스톤 상태 업데이트
"""

import re
from typing import Optional


def parse_challenge_command(text: str) -> Optional[dict]:
    """
    챌린지 관련 명령어를 파싱합니다.

    Returns:
        None — 챌린지 명령이 아닌 경우
        dict — {
            "command": "STATUS" | "ADD_EARNING" | "COMPLETE_MILESTONE",
            ... command-specific fields
        }
    """
    text = text.strip()

    # 1. 챌린지 현황 조회
    status_patterns = [
        r"챌린지\s*(현황|상태|진행|어떻게|어때)",
        r"(현황|상태|진행률?)\s*알려",
        r"수익\s*(현황|상태|얼마)",
        r"목표\s*(현황|달성률?|어디까지)",
        r"(얼마나?\s*모았|얼마\s*벌었)",
    ]
    for pattern in status_patterns:
        if re.search(pattern, text):
            return {"command": "STATUS"}

    # 2. 수익 등록
    # 패턴: "수익 등록 5000원 앱스토어", "5000원 수익 등록", "수익 5000원"
    earning_patterns = [
        r"수익\s*(?:등록|추가|기록)?\s*(\d[\d,]*)원?\s*(.*)?",
        r"(\d[\d,]*)원?\s*(?:수익|벌었|벌림|매출)\s*(?:등록|추가|기록)?\s*(.*)?",
        r"(?:등록|추가|기록)\s*(?:수익)?\s*(\d[\d,]*)원?\s*(.*)?",
    ]
    for pattern in earning_patterns:
        m = re.search(pattern, text)
        if m:
            amount_str = m.group(1).replace(",", "")
            amount = int(amount_str)
            source = (m.group(2) or "").strip()
            # Clean source of filler words
            for filler in ["에서", "으로", "해줘", "해", "줘", "좀", "부터"]:
                source = source.replace(filler, "").strip()
            return {
                "command": "ADD_EARNING",
                "amount": amount,
                "source": source if source else None,
            }

    # 3. 마일스톤 완료
    milestone_patterns = [
        r"마일스톤\s*(?:완료|달성|끝|클리어)\s*(.*)?",
        r"(.*)\s*마일스톤\s*(?:완료|달성|끝|클리어)",
        r"(수익\s*모델\s*확정|MVP\s*출시|첫\s*수익\s*발생|10만원?\s*달성)\s*(?:완료|달성|끝|했)",
    ]
    for pattern in milestone_patterns:
        m = re.search(pattern, text)
        if m:
            milestone_name = (m.group(1) or "").strip()
            for filler in ["해줘", "해", "줘", "좀", "했어", "됐어"]:
                milestone_name = milestone_name.replace(filler, "").strip()
            return {
                "command": "COMPLETE_MILESTONE",
                "milestone_name": milestone_name,
            }

    return None
