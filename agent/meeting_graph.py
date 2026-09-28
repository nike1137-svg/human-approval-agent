"""그래프 ① 회의록 그래프 v3 — 회의록 한 편에 한 번 (thread_id = 회의록 id).

    줄 분류(라우팅 · 노드 4) → 할 일 뽑기(그라운딩 · 값마다 인용 · 날짜 도구 호출) ⇄ 날짜 도구
      → 정리(코드 · 날짜 도구 결과와 맞춰 봄) → 대조(LLM · 같은 담당자 쌍의 중복만)
      → 검수(LLM-as-Judge · 노드 2 · 네 질문) → 가드레일(Send 로 할 일마다 · 코드) + 할 일 후보(H14 · 코드)

v3 (design.md 8-7): 값마다 근거를 붙이고 **코드가 그 근거로 값을 확인**한다. v2 에서 LLM 에 더 맡긴 부분
(빠진 줄 대조 · 검수 아니오의 인용 요구 · 신호)은 측정에서 나빠져 v1 방식으로 되돌렸다. 옛 그래프는 agent/meeting_graph_v1.py

끝나면 상태의 「검사결과」 에 할 일마다 {내용 · 담당자 · 인용들 · 마감 · 근거 · 연락대상 · 검수 · 걸린규칙} 이 남는다.
그다음 할 일마다 그래프 ②(할 일 그래프)를 따로 시작한다 — 한 그래프로 하면 자동 건 등록까지 멈추기 때문
(tests/test_langgraph_behavior.py 시험 1).

모델: gpt-4o-mini · 온도 0. 환경 변수 HITL_MODEL 로 바꿀 수 있다.
(09-28 gpt-5.6-luna 도 시험: 줄 분류는 됐지만 chat completions 에서 「추론 설정 + 함수 도구」 를 함께 쓸 수 없어 뽑기에서 400 오류.
 작성자 결정 — 시운전에서 문제없던 gpt-4o-mini 유지)
부르기 전마다 비용 차단기(agent/cost.py)가 누적 상한(5달러)을 검사한다.
"""
from __future__ import annotations

import json
import operator
import os
from datetime import date
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Send
from pydantic import BaseModel, Field

from agent import meeting
from agent.cost import 차단기
from agent.dates import 날짜계산
from agent.meeting import 루트
from agent.rules import 검사, 검수질문, 검수통과, 마감고치기, 부탁말, 비교용규칙, 아니오아닌것

load_dotenv(루트 / ".env")
모델 = os.environ.get("HITL_MODEL", "gpt-4o-mini")
뽑기_최대반복 = 6  # 날짜 도구를 오가는 횟수 상한 (비용 폭주 방지)

_llm = None


def llm():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model=모델, temperature=0)
    return _llm


def _부르기(메시지: list, 단계: str, 회의id: str, 도구=None, 구조=None):
    """차단기 확인 → 호출 → 실제 토큰 기록. 구조가 있으면 (원본 메시지, 파싱 결과)."""
    차단기.확인(모델)
    if 구조 is not None:
        r = llm().with_structured_output(구조, include_raw=True).invoke(메시지)
        차단기.기록(모델, r["raw"].usage_metadata, 단계, 회의id)
        return r["raw"], r["parsed"]
    바인딩 = llm().bind_tools(도구) if 도구 else llm()
    r = 바인딩.invoke(메시지)
    차단기.기록(모델, r.usage_metadata, 단계, 회의id)
    return r, None


def _번호원문(m: meeting.회의) -> str:
    return "\n".join(f"{i + 1}. {l}" for i, l in enumerate(m.줄들))


def _머리(m: meeting.회의) -> str:
    요일 = "월화수목금토일"[date.fromisoformat(m.회의일).weekday()]
    기준 = " · ".join(f"{k} {v}" for k, v in (m.기준날짜 or {}).items()) or "없음"
    return (f"회의일: {m.회의일} ({요일})\n참석자: {', '.join(m.참석자)}\n역할: {m.역할}\n"
            f"기준 날짜: {기준}\n팀: {', '.join(meeting.팀)} (그 밖의 사람 · 기관은 바깥)")


# ───────────────────────── 상태 ─────────────────────────
class 회의상태(TypedDict, total=False):
    회의id: str
    분류: list[dict]                                   # [{"번호": 1, "종류": "할일"}, ...]
    메시지: Annotated[list, add_messages]               # 뽑기 ⇄ 날짜 도구 대화
    반복: int
    할일들: list[dict]                                  # 뽑힌 할 일 (정리 · 대조 · 검수 결과가 붙음) + 대조가 만든 후보
    도구기록: list[dict]                                # 날짜 도구가 돌려준 값들
    대조기록: dict                                      # 대조 노드가 본 쌍과 답 (화면 · 분석용)
    뽑기경고: list[str]                                 # 모양이 틀려 버린 뽑기 항목의 원문 (정리 노드)
    검사결과: Annotated[list[dict], operator.add]        # 가드레일이 할 일마다 하나씩 보탬


class 가드레일입력(TypedDict):
    회의id: str
    할일: dict


# ───────────────────────── ① 줄 분류 (라우팅) ─────────────────────────
class LineKind(BaseModel):
    number: int = Field(description="줄 번호")
    kind: Literal["task", "done", "undecided", "conditional", "report", "chat"] = Field(
        description="task=할 일을 정하거나 맡거나 마감을 말함(수락 · 담당 변경 포함) / done=이미 끝난 일 / "
                    "undecided=결정 안 됨 · 보류 · 다음에 다시 · 다음 기수 이야기 / conditional=조건이 충족되면 하는 일 / "
                    "report=진행 상황 보고 · 의견 · 제안 / chat=잡담 · 인사")


class ClassifyResult(BaseModel):
    lines: list[LineKind]


분류지시 = """회의록의 각 줄을 한 가지 종류로 분류한다. 모든 줄 번호에 대해 답한다. 줄은 앞뒤 줄과 이어서 읽는다.
- task: 누가 무엇을 하기로 정하거나, 맡겠다고 하거나, 담당을 바꾸거나, 마감을 말하는 줄.
  부탁에 대한 대답 · 수락(「네, ~할게요」 · 「~드릴게요」 · 「~해 둘게요」)도 task 다.
  사투리 미래형(「~께예」 · 「~하께예」 · 「~주께예」)도 앞으로 하겠다는 말이므로 task 다.
- done: 이미 끝난 일을 알리는 줄. 과거형(「~했어요」 · 「~보냈어요」 · 「~잡아 놨어요」 · 「~끝났어요」)일 때만 done 이다
- undecided: 아직 결정하지 않았거나, 보류하거나, 다음에 다시 이야기하자거나, 다음 기수(다음번 프로그램) 이야기
- conditional: 어떤 조건이 충족되면 하겠다는 줄
- report: 진행 상황 보고, 의견, 제안(누가 맡는다는 말이 없는 것)
- chat: 잡담, 인사"""


def 분류(state: 회의상태):
    m = meeting.읽기(state["회의id"])
    _, r = _부르기([SystemMessage(분류지시), HumanMessage(f"{_머리(m)}\n\n{_번호원문(m)}")], "분류", m.id, 구조=ClassifyResult)
    종류표 = {"task": "할일", "done": "끝난일", "undecided": "미확정", "conditional": "조건부", "report": "보고", "chat": "잡담"}
    return {"분류": [{"번호": x.number, "종류": 종류표[x.kind]} for x in r.lines]}


def 분류뒤(state: 회의상태) -> str:
    # 라우팅은 줄을 버리지 않고 표시만 한다 (09-28 M1 시운전: 버리는 방식이 진짜 할 일 4건을 없앰).
    # 잡담 · 인사만 있는 회의록이면 뽑기를 건너뛴다
    return "뽑기" if any(x["종류"] != "잡담" for x in state["분류"]) else END


# ───────────────────────── ② 할 일 뽑기 (그라운딩 + 날짜 도구) ─────────────────────────
@tool
def calc_date(expression: str, meeting_date: str) -> str:
    """마감 표현(예: '이번 주 금요일까지', '낼까지', '10월 2일', '개강 전날까지')을 회의일 기준 날짜로 바꾼다.
    '개강 날 · 개강 전날' 은 회의록 머리의 기준 날짜로 계산한다. 날짜로 정할 수 없는 표현이면 date 가 null 이고
    kind 가 그 까닭이다 (모호 · 기준필요 · 못읽음 · 없음). meeting_date 는 YYYY-MM-DD."""
    return json.dumps(날짜계산(expression, meeting_date), ensure_ascii=False)


class TaskItem(BaseModel):
    content: str = Field(description="할 일 (짧게)")
    owner: str | None = Field(description="담당자 이름. 회의록으로 정할 수 없으면 null")
    owner_quote: str | None = Field(description="담당자를 정한 말을 근거 줄에서 글자 그대로 복사 (예: '민호 씨가' · '제가' · '해 주이소'). owner 가 null 이면 null")
    owner_basis: Literal["name", "self", "requested", "guess"] = Field(
        description="name=근거에 담당자 이름이 나옴 / self=담당자 본인이 「제가 ~할게요」 라고 맡음 / "
                    "requested=다른 사람이 부탁해서 담당자가 맡음 / guess=근거로 정할 수 없어 추정")
    due_text: str | None = Field(description="회의록에 나온 마감 표현 그대로. 없으면 null")
    due: str | None = Field(description="calc_date 가 돌려준 날짜(YYYY-MM-DD). 도구가 null 이면 null")
    evidence: list[str] = Field(description="근거 줄. 회의록 줄을 「이름: 말」 통째로, 글자 하나 바꾸지 말고 복사 (번호는 빼고)")
    contact: Literal["none", "team", "outside"] = Field(
        description="이 할 일을 하면서 연락 · 안내 · 전달하는 대상. none=없음 / team=팀 사람에게만 / outside=팀 밖의 사람 · 기관")
    contact_quote: str | None = Field(description="연락 대상을 가리키는 말을 근거 줄에서 글자 그대로 복사. contact 가 none 이면 null")


@tool
def submit_tasks(tasks: list[TaskItem]) -> str:
    """뽑은 할 일 목록을 제출한다. 모든 마감 표현을 calc_date 로 바꾼 뒤 마지막에 한 번 부른다."""
    return "받음"


뽑기지시 = """회의록에서 할 일을 뽑는다. 회의록에 없는 것은 만들지 않는다 (그라운딩).
- 줄마다 붙은 [종류] 표시는 앞 단계의 판단이다. 참고하되 그대로 믿지 않는다.
  [끝난일] · [보고] 표시가 있어도 앞으로 하겠다는 말(「~할게요」 · 「~드릴게요」 · 「~해 둘게요」 · 「~께예」)이면 할 일이다.
  이미 끝난 일(과거형) · 잡담 · 다음 기수 이야기는 할 일로 만들지 않는다.
- 같은 일을 여러 번 말했으면 할 일 하나로 묶고 관련 줄을 모두 근거에 넣는다.
- 담당자는 실제로 그 일을 하는 사람이다. 정할 수 없으면 null.
  부탁하는 말(「~해 주세요」 · 「~해 주이소」)이면 담당자는 말한 사람이 아니라 부탁받은 사람이다.
- 값마다 근거를 붙인다: 담당자는 owner_quote · owner_basis, 연락 대상은 contact · contact_quote. 인용은 근거 줄에서 글자 그대로.
- 마감 표현이 있으면 반드시 calc_date 도구로 날짜를 구한다. 직접 계산하지 않는다. 도구가 null 을 주면 due 도 null.
- 근거는 회의록 줄을 「이름: 말」 통째로 복사한다. 줄 번호는 빼고, 글자를 바꾸지 않는다.
- 다 끝나면 submit_tasks 를 한 번 부른다."""


def 뽑기(state: 회의상태):
    m = meeting.읽기(state["회의id"])
    반복 = state.get("반복", 0)
    메시지 = state.get("메시지") or []
    새것 = []
    if not 메시지:
        분류표 = "\n".join(f"{x['번호']}. [{x['종류']}] {m.줄들[x['번호'] - 1]}" for x in state["분류"] if 0 < x["번호"] <= len(m.줄들))
        새것 = [SystemMessage(뽑기지시), HumanMessage(f"{_머리(m)}\n\n줄마다 분류된 회의록:\n{분류표}")]
    elif isinstance(메시지[-1], AIMessage) and not 메시지[-1].tool_calls:
        새것.append(HumanMessage("글로 답하지 말고 도구를 부른다. 결과는 submit_tasks 로 제출한다."))
    if 반복 >= 뽑기_최대반복:
        새것.append(HumanMessage("이제 submit_tasks 를 불러 지금까지의 결과를 제출한다."))
    r, _ = _부르기(메시지 + 새것, "뽑기", m.id, 도구=[calc_date, submit_tasks])
    return {"메시지": 새것 + [r], "반복": 반복 + 1}


def 뽑기뒤(state: 회의상태) -> str:
    마지막 = state["메시지"][-1]
    이름들 = [c["name"] for c in getattr(마지막, "tool_calls", [])]
    if "submit_tasks" in 이름들:
        return "정리"
    if "calc_date" in 이름들 and state.get("반복", 0) <= 뽑기_최대반복:
        return "날짜도구"
    return "정리" if state.get("반복", 0) > 뽑기_최대반복 else "뽑기"


def 날짜도구(state: 회의상태):
    m = meeting.읽기(state["회의id"])
    마지막: AIMessage = state["메시지"][-1]
    답들, 기록 = [], list(state.get("도구기록") or [])
    for c in 마지막.tool_calls:
        if c["name"] == "calc_date":
            # 기준 날짜(개강일 등)는 LLM 이 넘기지 않고 코드가 회의록 머리에서 넣는다
            결과 = 날짜계산(c["args"].get("expression", ""), c["args"].get("meeting_date", "") or m.회의일, m.기준날짜)
            기록.append({"표현": c["args"].get("expression"), **결과})
            답들.append(ToolMessage(json.dumps(결과, ensure_ascii=False), tool_call_id=c["id"]))
        else:
            답들.append(ToolMessage("먼저 calc_date 결과를 받은 뒤 submit_tasks 를 다시 부른다.", tool_call_id=c["id"]))
    return {"메시지": 답들, "도구기록": 기록}


_담당근거 = {"name": "이름", "self": "제가", "requested": "부탁받음", "guess": "추정"}
_연락 = {"none": "없음", "team": "팀", "outside": "바깥"}


def _풀기(x):
    """LLM 이 객체 대신 JSON 글자로 보낸 것을 푼다 (09-28 v3 측정 첫 회에 실제로 옴 → 정리 노드에서 멈춤). 못 풀면 None."""
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError:
            return None
    return x


def _제출(state: 회의상태) -> tuple[list[dict], list[str]]:
    """(할 일 목록, 버린 항목의 원문). 모양이 틀린 항목은 버리고 원문을 남긴다 —
    그 근거 줄은 H14(분류는 할 일인데 근거에 없는 줄)가 후보로 사람에게 보낸다."""
    for msg in reversed(state.get("메시지") or []):
        for c in getattr(msg, "tool_calls", []) or []:
            if c["name"] == "submit_tasks":
                목록 = _풀기(c["args"].get("tasks", []))
                if not isinstance(목록, list):
                    return [], [str(c["args"].get("tasks"))[:500]]
                할일들, 버림 = [], []
                for 원 in 목록:
                    t = _풀기(원)
                    if not isinstance(t, dict):
                        버림.append(str(원)[:500])
                        continue
                    할일들.append({"내용": t.get("content"), "담당자": t.get("owner"), "담당_인용": t.get("owner_quote"),
                                 "담당_근거": _담당근거.get(t.get("owner_basis"), "추정"),
                                 "마감_원문": t.get("due_text"), "마감": t.get("due"), "근거": list(t.get("evidence") or []),
                                 "연락대상": _연락.get(t.get("contact"), "없음"), "연락_인용": t.get("contact_quote")})
                return 할일들, 버림
    return [], []


# ───────────────────────── ③ 정리 (코드 · 0원) ─────────────────────────
def 정리(state: 회의상태):
    """LLM 이 낸 값을 날짜 도구 결과와 맞춰 본다 — 값을 고치지 않고 확인한 사실만 붙인다."""
    m = meeting.읽기(state["회의id"])
    도구날짜 = {x["날짜"] for x in state.get("도구기록") or [] if x.get("날짜")}
    할일들, 버림 = _제출(state)
    for t in 할일들:
        # 마감이 있는데 날짜 도구가 돌려준 적 없는 날짜면 LLM 이 직접 쓴 것 (C12)
        t["마감_직접씀"] = bool(t.get("마감")) and t["마감"] not in 도구날짜
        t["마감_종류"] = 날짜계산(t["마감_원문"], m.회의일, m.기준날짜)["종류"] if t.get("마감_원문") else "없음"
    # 근거에 있는 마감 표현을 날짜 도구로 다시 계산해, LLM 이 잘못 옮긴 마감은 코드가 바로잡는다 (못 고치는 건은 C 규칙이 멈춤)
    return {"할일들": [마감고치기(t, m) for t in 할일들], "뽑기경고": 버림}


# ───────────────────────── ④ 대조 (LLM · 같은 담당자 쌍의 중복만 · 쌍이 없으면 부르지 않음) ─────────────────────────
class PairCheck(BaseModel):
    a: int = Field(description="앞 할 일 번호")
    b: int = Field(description="뒤 할 일 번호")
    same: bool = Field(description="두 할 일이 같은 일인가 (같은 일을 두 번 뽑음)")
    reason: str = Field(description="판단 이유 한 줄")


class CrossCheckResult(BaseModel):
    pairs: list[PairCheck]


대조지시 = """다른 사람이 회의록에서 뽑은 할 일 목록을 회의록 원문과 대조한다.
주어진 「같은 담당자의 할 일 쌍」 마다 — 같은 일을 두 번 뽑은 것인가 (same) 를 답한다. 비슷해도 다른 일이면 false.
주어진 쌍 모두에 답한다."""


def 대조(state: 회의상태):
    """v3: 중복만 LLM 에 묻는다 (R4-마). 빠진 줄은 v1 H14 방식(코드)으로 — v2 의 빠진 줄 대조는 측정에서 나빠짐 (8-7 원인 1)."""
    m = meeting.읽기(state["회의id"])
    할일들 = [dict(t) for t in state.get("할일들") or []]
    쌍들 = [(i + 1, j + 1) for i in range(len(할일들)) for j in range(i + 1, len(할일들))
            if 할일들[i].get("담당자") and 할일들[i].get("담당자") == 할일들[j].get("담당자")]
    if not 쌍들:
        return {"할일들": 할일들, "대조기록": {"쌍": [], "답": None}}
    목록 = "\n".join(f"[{i + 1}] {json.dumps({k: t.get(k) for k in ['내용', '담당자', '마감_원문', '근거']}, ensure_ascii=False)}"
                   for i, t in enumerate(할일들))
    묻는쌍 = "\n".join(f"({a}, {b})" for a, b in 쌍들)
    _, r = _부르기([SystemMessage(대조지시), HumanMessage(
        f"{_머리(m)}\n\n회의록:\n{_번호원문(m)}\n\n뽑힌 할 일:\n{목록}\n\n같은 담당자의 할 일 쌍:\n{묻는쌍}")],
        "대조", m.id, 구조=CrossCheckResult)
    for p in r.pairs:   # 같다고 본 쌍의 뒤의 것에 표시 (I15)
        if p.same and (p.a, p.b) in 쌍들:
            할일들[p.b - 1]["중복_앞건"] = p.a
            할일들[p.b - 1]["중복_이유"] = p.reason
    return {"할일들": 할일들, "대조기록": {"쌍": 쌍들, "답": [p.model_dump() for p in r.pairs]}}


H14_좁힘 = False   # design.md 8-8 채택 기준을 통과하면 True (저장된 v3 원본 두 회차로 판정)


def _화자말(줄: str) -> tuple[str, str]:
    화자, _, 말 = meeting.줄정리(줄).partition(": ")
    return 화자, 말


def _덮였나(n: int, m: meeting.회의, 할일들: list[dict], 좁힘: bool) -> bool:
    """회의록 n번째 줄(1부터)이 뽑힌 할 일의 근거로 쓰였나."""
    줄 = meeting.줄정리(m.줄들[n - 1])
    근거들 = [(t, meeting.줄정리(x)) for t in 할일들 for x in t.get("근거") or []]
    if any(줄 == x for _, x in 근거들):
        return True
    if not 좁힘:
        return False
    화자, 말 = _화자말(줄)
    # ① 근거를 고쳐 적음 — 같은 화자의 근거 말(10자 이상)이 이 줄의 말 안에 그대로 있음 (M1 「좋습니다.」 를 빼고 옮김)
    for _, x in 근거들:
        h, 근거말 = _화자말(x)
        if h == 화자 and len(근거말) >= 10 and 근거말 in 말:
            return True
    # ② 부탁 → 수락 — 이 줄이 부탁하는 말이고 담당자 이름이 들어 있고, 바로 다음 줄이 그 담당자의 말로 그 할 일의 근거에 있음
    if n < len(m.줄들) and 부탁말.search(말):
        다음 = meeting.줄정리(m.줄들[n])
        for t, x in 근거들:
            담당 = (t.get("담당자") or "").strip()
            if 담당 and x == 다음 and _화자말(다음)[0] == 담당 and 담당 in 말:
                return True
    return False


def 누락후보(m: meeting.회의, 분류: list[dict], 할일들: list[dict], 좁힘: bool | None = None) -> list[dict]:
    """H14 — 줄 분류는 「할일 · 조건부」 인데 뽑힌 할 일 어느 근거에도 없는 줄을 「할 일 후보」 로 만든다 (LLM 없음 · v1 방식).
    덮였는지는 근거 줄과 **글자가 같은지**로 본다. 좁힘(8-8)이면 ① 고쳐 적은 근거 ② 부탁 → 수락 줄도 덮인 것으로 본다."""
    좁힘 = H14_좁힘 if 좁힘 is None else 좁힘
    후보들 = []
    for x in 분류:
        if x["종류"] in ("할일", "조건부") and 0 < x["번호"] <= len(m.줄들):
            줄 = m.줄들[x["번호"] - 1]
            if not _덮였나(x["번호"], m, 할일들, 좁힘):
                후보들.append({"내용": f"(할 일 후보 · 뽑기에서 빠짐) {줄.split(': ', 1)[-1]}", "담당자": None,
                             "마감_원문": None, "마감": None, "근거": [줄], "후보": True, "후보종류": "분류할일",
                             "검수": None, "마감_직접씀": False, "연락대상": "없음"})
    return 후보들


# ───────────────────────── ⑤ 검수 (LLM-as-Judge · 네 질문 · v1 방식 + 2-바 · 3-나) ─────────────────────────
class ReviewItem(BaseModel):
    number: int
    owner_ok: bool = Field(description=검수질문["담당자"])
    due_ok: bool = Field(description=검수질문["마감"])
    evidence_ok: bool = Field(description=검수질문["근거"])
    confirmed: bool = Field(description=검수질문["확정"])
    reason: str = Field(description="하나라도 false 면 그 이유 한 줄. 모두 true 면 빈 문자열")


class ReviewResult(BaseModel):
    items: list[ReviewItem]


검수지시 = f"""다른 사람이 회의록에서 뽑은 할 일을 회의록 원문과 대조해 검수한다. 할 일마다 네 질문에 true / false 로 답한다.
1. owner_ok: {검수질문['담당자']}
2. due_ok: {검수질문['마감']}
3. evidence_ok: {검수질문['근거']}
4. confirmed: {검수질문['확정']}
다음은 false 의 이유가 아니다: {' · '.join(아니오아닌것)}.
확신이 없으면 false 로 답하고 이유를 적는다."""


def 검수(state: 회의상태):
    m = meeting.읽기(state["회의id"])
    할일들 = [dict(t) for t in state.get("할일들") or []]
    후보들 = 누락후보(m, state.get("분류") or [], 할일들)
    if not 할일들:
        return {"할일들": 후보들}
    목록 = "\n".join(f"[{i + 1}] {json.dumps({k: t.get(k) for k in ['내용', '담당자', '마감_원문', '마감', '근거']}, ensure_ascii=False)}"
                   for i, t in enumerate(할일들))
    _, r = _부르기([SystemMessage(검수지시), HumanMessage(f"{_머리(m)}\n\n회의록:\n{_번호원문(m)}\n\n뽑힌 할 일:\n{목록}")],
                  "검수", m.id, 구조=ReviewResult)
    표 = {x.number: x for x in r.items}
    for i, t in enumerate(할일들):
        x = 표.get(i + 1)
        t["검수"] = ({"담당자": x.owner_ok, "마감": x.due_ok, "근거": x.evidence_ok, "확정": x.confirmed, "이유": x.reason}
                   if x else {"답없음": True, "이유": "검수 답이 없음"})
    return {"할일들": 할일들 + 후보들}


def 나누기(state: 회의상태):
    할일들 = state.get("할일들") or []
    return [Send("가드레일", {"회의id": state["회의id"], "할일": t}) for t in 할일들] or END


# ───────────────────────── ⑥ 가드레일 (코드 · Send 로 할 일마다) ─────────────────────────
def 가드레일(state: 가드레일입력):
    m = meeting.읽기(state["회의id"])
    t = dict(state["할일"])
    t["검수_인정"] = 검수통과(t)[1]   # 인용이 확인되어 인정된 아니오 (승인 화면에 보여 줌)
    전부 = 검사(t, m)
    # 걸린규칙 = 실제로 멈추게 하는 규칙 (그래프 ② 가 이것으로 갈린다). 비교용(C13)은 따로 — 측정 때 채점기가 다시 계산해 비교한다
    t["걸린규칙"] = [r for r in 전부 if r not in 비교용규칙]
    t["비교규칙"] = [r for r in 전부 if r in 비교용규칙]
    return {"검사결과": [t]}


def 만들기(checkpointer=None):
    g = StateGraph(회의상태)
    g.add_node("분류", 분류)
    g.add_node("뽑기", 뽑기)
    g.add_node("날짜도구", 날짜도구)
    g.add_node("정리", 정리)
    g.add_node("대조", 대조)
    g.add_node("검수", 검수)
    g.add_node("가드레일", 가드레일)
    g.add_edge(START, "분류")
    g.add_conditional_edges("분류", 분류뒤, ["뽑기", END])
    g.add_conditional_edges("뽑기", 뽑기뒤, ["날짜도구", "정리", "뽑기"])
    g.add_edge("날짜도구", "뽑기")
    g.add_edge("정리", "대조")
    g.add_edge("대조", "검수")
    g.add_conditional_edges("검수", 나누기, ["가드레일", END])
    g.add_edge("가드레일", END)
    return g.compile(checkpointer=checkpointer)
