"""날짜 도구 — 「이번 주 금요일」 같은 말을 회의일 기준 날짜로 바꾼다. LLM 이 **스스로 부르는** 도구다 (도구 호출 패턴).

LLM 이 날짜를 직접 계산하지 않게 하려는 것 (기준 C · 규칙 C10 의 원인을 구조로 줄임).
바꿀 수 없는 말(「다음 주쯤」 · 「퍼뜩」 · 「휴가 가기 전에」 · 「개강 전에」)은 날짜를 만들지 않고 None 을 돌려준다.
「전날」 처럼 기준 날짜가 필요한 말은 None 과 함께 「날짜를 직접 적은 표현으로 다시 부르라」 는 풀이를 돌려준다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

요일 = "월화수목금토일"


def 날짜계산(표현: str, 회의일: str) -> dict:
    """{"날짜": "YYYY-MM-DD" | None, "풀이": str}"""
    d0 = date.fromisoformat(회의일)
    s = re.sub(r"\s+", " ", 표현 or "").strip()
    s = re.sub(r"(까지|부터|에|중으로|중|오전|오후|안으로)$", "", s).strip()
    s = re.sub(r"(까지|부터|에|중으로|중|오전|오후)$", "", s).strip()  # 「오늘 중으로」 처럼 두 겹
    월요일 = d0 - timedelta(days=d0.weekday())

    def 답(d: date, 풀이: str) -> dict:
        return {"날짜": d.isoformat(), "풀이": f"{풀이} → {d.isoformat()} ({요일[d.weekday()]})"}

    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if m:
        return 답(date(d0.year, int(m.group(1)), int(m.group(2))), "날짜를 직접 말함")
    if re.search(r"(쯤|조만간|가능하면|빨리|퍼뜩|언능|전에|후에|나오면|되면|안에)", s) or re.fullmatch(r"(다음|이번) ?주", s):
        return {"날짜": None, "풀이": "날짜로 정할 수 없는 표현 — 마감을 비워 둔다"}
    if "전날" in s or "다음날" in s or "그날" in s:
        return {"날짜": None, "풀이": "기준 날짜가 필요한 표현 — 기준이 회의록에 날짜로 있으면 그 날짜를 적어 다시 부른다 (예: 11월 3일)"}
    if s in ("오늘", "당일"):
        return 답(d0, "오늘")
    if s in ("낼모레", "모레"):
        return 답(d0 + timedelta(days=2), "모레")
    if s in ("내일", "낼"):
        return 답(d0 + timedelta(days=1), "내일")
    m = re.fullmatch(r"(이번|다음|다다음) ?주 ?([월화수목금토일])요일", s)
    if m:
        주 = {"이번": 0, "다음": 1, "다다음": 2}[m.group(1)]
        return 답(월요일 + timedelta(days=7 * 주 + 요일.index(m.group(2))), f"{m.group(1)} 주 {m.group(2)}요일")
    m = re.fullmatch(r"([월화수목금토일])요일", s)
    if m:
        차 = (요일.index(m.group(1)) - d0.weekday()) % 7 or 7  # 회의일과 같은 요일이면 다음 주
        return 답(d0 + timedelta(days=차), f"다가오는 {m.group(1)}요일")
    return {"날짜": None, "풀이": "알 수 없는 표현 — 마감을 비워 둔다"}
