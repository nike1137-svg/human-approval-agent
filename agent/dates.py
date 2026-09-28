"""날짜 도구 — 「이번 주 금요일」 같은 말을 회의일 기준 날짜로 바꾼다. LLM 이 **스스로 부르는** 도구다 (도구 호출 패턴).

LLM 이 날짜를 직접 계산하지 않게 하려는 것 (기준 C 의 원인을 구조로 줄임).
v2 (09-28 밤): 측정 원본에서 LLM 이 실제로 넘긴 표현을 보니 문장 전체(「…오늘 중으로 알려드리겠심더.」)나
끝에 「요」 · 동사가 붙은 말(「금요일까지요」 · 「오늘 보낼게요」)이 많았다 → **문장 안에서 찾고**, 회의록 머리의
개강일 · 마지막 수업일로 「개강 날 · 개강 전날」 을 계산한다. 결과에 **종류**를 붙여 기준 C5 가 쓴다:

    날짜      — 날짜로 바꿈
    모호      — 원래 모호한 표현 (쯤 · 가능하면 · 빨리 · 조만간 · 퍼뜩 · 안에 · 나오면 · 되면). 날짜를 비우는 것이 맞음
    기준필요  — 「전날 · 그날 · 수업 전」 처럼 기준 날짜가 있어야 하는 표현
    못읽음    — 날짜 말은 있는데 읽지 못함
    없음      — 날짜 말이 없음
"""
from __future__ import annotations

import re
from datetime import date, timedelta

요일 = "월화수목금토일"
_요일 = r"([월화수목금토일])요일"


def _답(d: date, 풀이: str) -> dict:
    return {"날짜": d.isoformat(), "종류": "날짜", "풀이": f"{풀이} → {d.isoformat()} ({요일[d.weekday()]})"}


def _없음(종류: str, 풀이: str) -> dict:
    return {"날짜": None, "종류": 종류, "풀이": 풀이}


def 날짜계산(표현: str, 회의일: str, 기준: dict | None = None) -> dict:
    """{"날짜": "YYYY-MM-DD" | None, "종류": ..., "풀이": str}. 기준 = {"개강": "YYYY-MM-DD", "마지막 수업": ...}"""
    d0 = date.fromisoformat(회의일)
    기준 = {k: date.fromisoformat(v) for k, v in (기준 or {}).items() if v}
    s = re.sub(r"\s+", " ", 표현 or "").strip()
    월요일 = d0 - timedelta(days=d0.weekday())

    # 1) 날짜를 직접 말함 — 「10월 16일」
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if m:
        return _답(date(d0.year, int(m.group(1)), int(m.group(2))), "날짜를 직접 말함")
    # 2) 원래 모호한 표현 — 날짜를 만들지 않는 것이 맞다
    if re.search(r"(쯤|조만간|가능하면|빨리|퍼뜩|언능|이번 ?주 ?안|이번 ?주 ?중|나오면|되면|되는 대로|휴가 가기 전)", s):
        return _없음("모호", "원래 모호한 표현 — 마감을 비워 둔다")
    # 3) 기준 날짜로 계산 — 「개강 날 · 개강 전날 · 마지막 수업 날」
    for 이름, 날 in 기준.items():
        if re.search(이름.replace(" ", r" ?") + r" ?(전날|하루 전|전에|전까지)", s):
            return _답(날 - timedelta(days=1), f"{이름} 전날 (「{이름} 전에」 도 전날로 봄)")
        if re.search(이름.replace(" ", r" ?") + r" ?(날|당일|하는 날)", s):
            return _답(날, f"{이름} 날")
    # 4) 기준이 있어야 하는 표현
    if re.search(r"(전날|그날|다음날|수업 ?전|시작 ?전|(?<!오)전에)", s):   # 「오전에」 는 빼기
        return _없음("기준필요", "기준 날짜가 필요한 표현 — 기준이 회의록에 날짜로 있으면 그 날짜를 넣어 다시 부른다 (예: 개강 전날 · 11월 3일)")
    # 5) 상대 날짜 — 문장 안에서 찾는다
    m = re.search(r"(이번|다음|다다음) ?주 ?" + _요일, s)
    if m:
        주 = {"이번": 0, "다음": 1, "다다음": 2}[m.group(1)]
        return _답(월요일 + timedelta(days=7 * 주 + 요일.index(m.group(2))), f"{m.group(1)} 주 {m.group(2)}요일")
    m = re.search(_요일, s)
    if m:
        차 = (요일.index(m.group(1)) - d0.weekday()) % 7 or 7  # 회의일과 같은 요일이면 다음 주
        return _답(d0 + timedelta(days=차), f"다가오는 {m.group(1)}요일")
    # 「낼」 은 한 낱말일 때만 (「보낼게요」 · 「올릴 낍니더」 안의 글자는 아님)
    if re.search(r"(?<![가-힣])(낼모레|모레)(?![가-힣])|(?<![가-힣])(낼모레|모레)(?=까지|에)", s):
        return _답(d0 + timedelta(days=2), "모레")
    if re.search(r"(?<![가-힣])(내일|낼)(?=\s|까지|에|중|$|[,.])", s):
        return _답(d0 + timedelta(days=1), "내일")
    if re.search(r"(오늘|당일)", s):
        return _답(d0, "오늘")
    # 6) 날짜 말은 있는데 못 읽음 / 없음
    if re.search(r"(까지|기한|마감|이번 ?주|다음 ?주|\S날)", s):
        return _없음("못읽음", "날짜 말은 있는데 읽지 못함 — 마감을 비워 둔다")
    return _없음("없음", "날짜 말이 없음")
