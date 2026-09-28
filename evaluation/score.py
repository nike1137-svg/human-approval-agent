"""채점기 — 뽑힌 할 일을 정답(data/gold.json)과 짝짓고, 멈춤 기준 구성별로 개입률 · 놓침 · 헛멈춤 · 비용을 센다.

짝짓기 (design.md 5절)
- 뽑힌 건의 근거 줄과 **겹치는 근거 줄**이 있는 정답 건을 찾는다. 여럿이면 담당자가 맞는 쪽 → 내용이 비슷한 쪽
- 짝이 없으면 **지어냄** (함정 줄에서 뽑았거나, 원문에 없는 근거) → 봐야함 = 예
- 같은 정답 건에 두 번째로 짝지어지면 **중복** → 봐야함 = 예
- 짝이 있어도 담당자 · 마감이 정답의 허용 목록 밖이면 **어긋남** → 봐야함 = 예
- 근거 줄이 회의록 원문에 글자 그대로 없으면 **어긋남(근거)** → 봐야함 = 예 (09-28 추가 · 마감이 빠진 것도 어긋남 그대로)
- 짝지어지지 않은 정답 건 = **뽑기 누락** (HITL 이 잡을 수 없는 문제 — 비교표와 따로 센다)

고르는 법 (design.md 7절): 비용 = (놓침 + 누락) × 10 + 헛멈춤 → 가장 작은 구성. 「기준 없음」 · 「전부 멈춤」 은 기준점.
(누락을 비용에 넣은 것은 H14 를 더한 09-28 부터 — H14 는 누락을 되찾는 기준이라 누락을 안 세면 헛멈춤만 보인다)

의도한 멈춤 (09-28 밤 작성자 ①-가): 봐야함 아니오인데 **업무 정책 규칙(F12)만으로** 멈춘 건은 헛멈춤이 아니다.
손실에 넣지 않고 멈춤 건수에는 센다. v1 · v2 모두 같은 채점기로 잰다 (전후 비교가 공정하게).

구성 = (이름, 켠 묶음, 선택). 선택: {"뺀규칙": {"C13"}, "할일아님": True/False}
- 뺀규칙: 걸려도 멈추지 않는 규칙 (C13 은 비교용 · 기본에서 뺌)
- 할일아님: 대조가 「할 일 아님」 이라 본 후보를 남기나(C-2 · True) 버리나(C-1 · False)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent.meeting import 줄정리, 회의
from agent.rules import 검사, 묶음, 묶음표, 비교용규칙, 정책규칙

루트 = Path(__file__).resolve().parent.parent
정답파일 = 루트 / "data" / "gold.json"
K = 10  # 놓침 1건 = 헛멈춤 10건 (작성자 · 측정 전 확정)

기본선택 = {"뺀규칙": set(비교용규칙), "할일아님": True}
# v1 (고치기 전) 규칙으로 채점할 때의 구성 — 기준선 208점을 다시 낼 때
구성들_v1 = [
    ("기준 없음 (전부 자동)", ""),
    ("원문 예시 A+B", "AB"),
    ("최종 A~H", "ABCDEFGH"),
    ("전부 멈춤 (H 없음)", "*"),
]
# v3 (8-7). v2 에서 재던 C-1 / C-2 · C13 변형은 v2 측정으로 끝남 (결과는 design.md 8-7)
구성들 = [
    ("기준 없음 (전부 자동)", ""),
    ("원문 예시 A+B", "AB"),
    ("최종 A~I", "ABCDEFGHI"),
    ("전부 멈춤 (H 없음)", "*"),
]


def 정답읽기() -> dict:
    return json.loads(정답파일.read_text(encoding="utf-8"))


def _사람(s: str | None) -> str | None:
    s = (s or "").strip()
    return s.removesuffix(" 씨").removesuffix("씨") or None


def _비슷함(a: str, b: str) -> float:
    """글자 두 개씩 묶어 겹치는 비율 (내용이 비슷한 정답 건 고르기용)."""
    ga = {a[i:i + 2] for i in range(len(a) - 1)}
    gb = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(ga & gb) / max(1, len(ga | gb))


@dataclass
class 채점건:
    할일: dict
    걸린규칙: list[str]
    짝: str | None          # 정답 id
    판정: str               # 정상 · 지어냄 · 중복 · 어긋남(담당자) · 어긋남(마감) · 어긋남(담당자 · 마감)
    봐야함: bool


@dataclass
class 회의채점:
    회의id: str
    건들: list[채점건] = field(default_factory=list)
    누락: list[str] = field(default_factory=list)          # H14 후보까지 쳤을 때 남은 누락
    누락_H없이: list[str] = field(default_factory=list)    # H14 가 없을 때의 누락 (뽑기만)
    누락_C1: list[str] = field(default_factory=list)       # 「할 일 아님」 후보를 버렸을 때(C-1)의 누락


def _할일아님(t: dict) -> bool:
    return t.get("후보종류") == "할일아님"


def 채점(m: 회의, 뽑힌: list[dict], 정답회의: dict, 검사함수=None) -> 회의채점:
    """일반 할 일을 먼저 짝짓고, 그다음 H14 「할 일 후보」 를 짝짓는다.
    후보가 아직 짝이 없는 정답 건과 근거 줄이 겹치면 → 누락을 되찾음 (봐야함 = 예)
    아니면(할 일이 아닌 줄 · 이미 뽑힌 건과 같은 줄) → 사람 시간을 쓴 것 (봐야함 = 아니오 → 멈추면 헛멈춤)
    후보는 「할 일 아님」 을 **맨 뒤에** 짝짓는다 — 그래야 C-1(버림)의 누락을 같은 채점에서 셀 수 있다.
    검사함수: 걸린 규칙을 다시 계산할 함수 (기본 v2 · 기준선은 agent.rules_v1.검사)"""
    검사함수 = 검사함수 or 검사
    일반 = [t for t in 뽑힌 if not t.get("후보")]
    후보건 = sorted([t for t in 뽑힌 if t.get("후보")], key=_할일아님)
    결과 = _일반채점(m, 일반, 정답회의, 검사함수)
    쓰임 = {c.짝 for c in 결과.건들 if c.짝 and c.판정 != "중복"}
    결과.누락_H없이 = [g["id"] for g in 정답회의["할일"] if g["id"] not in 쓰임]
    결과.누락_C1 = None
    for t in 후보건:
        if _할일아님(t) and 결과.누락_C1 is None:
            결과.누락_C1 = [g["id"] for g in 정답회의["할일"] if g["id"] not in 쓰임]
        근거 = {줄정리(x) for x in t.get("근거") or []}
        남은 = [g for g in 정답회의["할일"] if g["id"] not in 쓰임 and 근거 & {줄정리(x) for x in g["근거"]}]
        if 남은:
            쓰임.add(남은[0]["id"])
            결과.건들.append(채점건(t, 검사함수(t, m), 남은[0]["id"], "후보(되찾음)", True))
        else:
            결과.건들.append(채점건(t, 검사함수(t, m), None, "후보(헛)", False))
    결과.누락 = [g["id"] for g in 정답회의["할일"] if g["id"] not in 쓰임]
    if 결과.누락_C1 is None:
        결과.누락_C1 = list(결과.누락)
    return 결과


def _일반채점(m: 회의, 뽑힌: list[dict], 정답회의: dict, 검사함수=None) -> 회의채점:
    검사함수 = 검사함수 or 검사
    결과 = 회의채점(m.id)
    정답들 = 정답회의["할일"]
    쓰임: dict[str, int] = {}
    후보목록 = []
    for 할일 in 뽑힌:
        근거 = {줄정리(x) for x in 할일.get("근거") or []}
        후보 = [g for g in 정답들 if 근거 & {줄정리(x) for x in g["근거"]}]
        # 근거 줄이 같은 정답 건이 여럿이면 **내용이 비슷한 쪽** 먼저, 담당자는 동점일 때만 (09-28 M1 시운전에서 찾은 결함:
        # 담당자를 먼저 보면 「담당자가 틀린 건」 이 담당자가 같은 다른 정답 건과 짝지어져 정상으로 세어짐)
        후보.sort(key=lambda g: (round(_비슷함(할일.get("내용") or "", g["내용"]), 2),
                                 _사람(할일.get("담당자")) in [_사람(x) for x in g["담당자_허용"]]), reverse=True)
        후보목록.append((할일, 후보))
    # 짝이 확실한(후보가 적은) 건부터 짝을 정해, 같은 근거 줄을 쓰는 두 정답 건(M1-07 · M1-08)이 섞이지 않게 한다
    순서 = sorted(range(len(후보목록)), key=lambda i: len(후보목록[i][1]) or 99)
    배정: dict[int, tuple[str | None, str]] = {}
    for i in 순서:
        할일, 후보 = 후보목록[i]
        if not 후보:
            배정[i] = (None, "지어냄")
            continue
        남은 = [g for g in 후보 if g["id"] not in 쓰임]
        g = 남은[0] if 남은 else 후보[0]
        if g["id"] in 쓰임:
            배정[i] = (g["id"], "중복")
            continue
        쓰임[g["id"]] = i
        틀림 = []
        if _사람(할일.get("담당자")) not in [_사람(x) for x in g["담당자_허용"]]:
            틀림.append("담당자")
        if (할일.get("마감") or None) not in g["마감_허용"]:
            틀림.append("마감")
        배정[i] = (g["id"], f"어긋남({' · '.join(틀림)})" if 틀림 else "정상")
    # 근거 줄이 회의록 원문에 그대로 없으면 「어긋남(근거)」 (09-28 작성자 ⓐ-1: 틀린 인용을 승인 화면에 보여 주는 건은 사람이 봐야 함)
    원문줄 = {줄정리(x) for x in m.줄들}
    for i, (할일, _) in enumerate(후보목록):
        짝, 판정 = 배정[i]
        if 짝 and 판정 != "중복" and any(줄정리(x) not in 원문줄 for x in 할일.get("근거") or []):
            앞 = 판정[4:-1].split(" · ") if 판정.startswith("어긋남(") else []
            배정[i] = (짝, f"어긋남({' · '.join(앞 + ['근거'])})")
    봐야함표 = {g["id"]: g["봐야함"] for g in 정답들}
    for i, (할일, _) in enumerate(후보목록):
        짝, 판정 = 배정[i]
        봐야 = True if 판정 != "정상" else 봐야함표[짝]
        결과.건들.append(채점건(할일, 검사함수(할일, m), 짝, 판정, 봐야))
    결과.누락 = [g["id"] for g in 정답들 if g["id"] not in 쓰임]
    return 결과


def 멈추게한규칙(걸린규칙: list[str], 켠묶음: str, 뺀규칙: set | None = None) -> list[str]:
    뺀규칙 = 뺀규칙 or set()
    if 켠묶음 == "*":
        return list(걸린규칙) or ["*"]
    return [r for r in 걸린규칙 if 묶음(r) in 켠묶음 and r not in 뺀규칙]


def _멈춤(걸린규칙: list[str], 켠묶음: str, 뺀규칙: set | None = None) -> bool:
    return bool(멈추게한규칙(걸린규칙, 켠묶음, 뺀규칙))


def _의도한(c: 채점건, 켠묶음: str, 뺀규칙: set) -> bool:
    """봐야함 아니오인데 업무 정책 규칙만으로 멈춤 → 헛멈춤 아님 (①-가)."""
    r = 멈추게한규칙(c.걸린규칙, 켠묶음, 뺀규칙)
    return (not c.봐야함) and bool(r) and set(r) <= 정책규칙


def 비교표(채점들: list[회의채점], 구성목록: list[tuple] | None = None) -> list[dict]:
    """구성마다: H 가 없는 구성은 H14 후보가 **만들어지지 않은 것**으로 보고 후보를 빼고, 누락도 「H 없이」 로 센다.
    C-1 (할일아님 False) 이면 「할 일 아님」 후보를 빼고 누락도 「C-1」 로 센다.
    손실 점수 = (놓침 + 누락) × K + 헛멈춤 — 누락은 사람에게도 보드에도 안 나타나는 놓침이라 같은 무게로 센다.
    헛멈춤에는 의도한 멈춤(F12 만)을 넣지 않는다.
    (API 요금이 아니다. 강의 「놓침과 헛멈춤 중 어느 쪽이 더 비싼지」 를 계산하는 점수)"""
    줄 = []
    for 구성 in 구성목록 or 구성들:
        이름, 켠묶음 = 구성[0], 구성[1]
        선택 = {**기본선택, **(구성[2] if len(구성) > 2 else {})}
        뺀, 남김 = 선택["뺀규칙"], 선택["할일아님"]
        H켬 = "H" in 켠묶음
        건들 = [c for r in 채점들 for c in r.건들
                if (H켬 or not c.할일.get("후보")) and (남김 or not _할일아님(c.할일))]
        누락 = sum(len((r.누락 if 남김 else r.누락_C1) if H켬 else r.누락_H없이) for r in 채점들)
        멈춘 = [c for c in 건들 if _멈춤(c.걸린규칙, 켠묶음, 뺀)]
        놓침 = [c for c in 건들 if c.봐야함 and not _멈춤(c.걸린규칙, 켠묶음, 뺀)]
        의도 = [c for c in 멈춘 if _의도한(c, 켠묶음, 뺀)]
        헛 = [c for c in 멈춘 if not c.봐야함 and c not in 의도]
        줄.append({"구성": 이름, "전체": len(건들), "멈춤": len(멈춘), "놓침": len(놓침), "누락": 누락,
                   "헛멈춤": len(헛), "의도한 멈춤": len(의도), "손실": (len(놓침) + 누락) * K + len(헛)})
    return 줄


def 하나씩빼기(채점들: list[회의채점], 최종: str = "ABCDEFGHI") -> list[dict]:
    """최종에서 묶음 하나씩 뺐을 때 — 그 묶음이 없으면 놓침 · 누락이 얼마나 늘고 헛멈춤이 얼마나 주나 (묶음마다의 몫)."""
    return 비교표(채점들, [(f"{b} 뺌", 최종.replace(b, "")) for b in 최종])


def 묶음단독(채점들: list[회의채점]) -> list[dict]:
    """묶음 하나만 켰을 때 잡는 건 (봐야 할 건을 멈춤) · 헛멈춤. 비교용 규칙(C13)은 뺀다."""
    줄 = []
    for b, (이름, _) in 묶음표.items():
        # H14 후보는 H 가 있을 때만 생기는 건이라 H 단독에서만 센다
        건들 = [c for r in 채점들 for c in r.건들 if b == "H" or not c.할일.get("후보")]
        뺀 = set(비교용규칙)
        줄.append({"묶음": b, "이름": 이름, "잡음": sum(c.봐야함 and _멈춤(c.걸린규칙, b, 뺀) for c in 건들),
                   "헛멈춤": sum((not c.봐야함) and _멈춤(c.걸린규칙, b, 뺀) for c in 건들)})
    return 줄


def 요약(채점들: list[회의채점]) -> dict:
    건들 = [c for r in 채점들 for c in r.건들]
    세기: dict[str, int] = {}
    for c in 건들:
        세기[c.판정] = 세기.get(c.판정, 0) + 1
    return {"뽑힌 건": len(건들), "봐야함": sum(c.봐야함 for c in 건들), "판정": 세기,
            "누락": sum(len(r.누락) for r in 채점들), "누락_H없이": sum(len(r.누락_H없이) for r in 채점들),
            "누락_C1": sum(len(r.누락_C1) for r in 채점들)}
