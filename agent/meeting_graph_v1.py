"""그래프 ① 회의록 그래프 — 회의록 한 편에 한 번 (thread_id = 회의록 id).

    줄 분류(라우팅 · 노드 4) → 할 일 뽑기(그라운딩 · 날짜 도구 호출) ⇄ 날짜 도구
      → 검수(LLM-as-Judge · 노드 2 · 네 질문) → 가드레일(Send 로 할 일마다 · 코드)

끝나면 상태의 「검사결과」 에 할 일마다 {내용 · 담당자 · 마감_원문 · 마감 · 근거 · 검수 · 걸린규칙} 이 남는다.
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
from agent.dates_v1 import 날짜계산   # [보존본 v1 — 커밋 d121b57 그대로 · 고치기 전 기준선을 새 회의록(M7)에서 잴 때만]
from agent.rules_v1 import 검사, 검수질문
from agent.meeting import 루트

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
    return f"회의일: {m.회의일} ({요일})\n참석자: {', '.join(m.참석자)}\n역할: {m.역할}"


# ───────────────────────── 상태 ─────────────────────────
class 회의상태(TypedDict, total=False):
    회의id: str
    분류: list[dict]                                   # [{"번호": 1, "종류": "할일"}, ...]
    메시지: Annotated[list, add_messages]               # 뽑기 ⇄ 날짜 도구 대화
    반복: int
    할일들: list[dict]                                  # 뽑힌 할 일 (검수 결과가 붙음)
    도구기록: list[dict]                                # 날짜 도구가 돌려준 값들
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
    """마감 표현(예: '이번 주 금요일까지', '낼까지', '10월 2일')을 회의일 기준 날짜로 바꾼다.
    날짜로 정할 수 없는 표현이면 date 가 null 이다. meeting_date 는 YYYY-MM-DD."""
    return json.dumps(날짜계산(expression, meeting_date), ensure_ascii=False)


class TaskItem(BaseModel):
    content: str = Field(description="할 일 (짧게)")
    owner: str | None = Field(description="담당자 이름. 회의록으로 정할 수 없으면 null")
    due_text: str | None = Field(description="회의록에 나온 마감 표현 그대로. 없으면 null")
    due: str | None = Field(description="calc_date 가 돌려준 날짜(YYYY-MM-DD). 도구가 null 이면 null")
    evidence: list[str] = Field(description="근거 줄. 회의록 줄을 「이름: 말」 통째로, 글자 하나 바꾸지 말고 복사 (번호는 빼고)")


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


def 뽑기뒤(state:회의상태) -> str:
    마지막 = state["메시지"][-1]
    이름들 = [c["name"] for c in getattr(마지막, "tool_calls", [])]
    if "submit_tasks" in 이름들:
        return "검수"
    if "calc_date" in 이름들 and state.get("반복", 0) <= 뽑기_최대반복:
        return "날짜도구"
    return "검수" if state.get("반복", 0) > 뽑기_최대반복 else "뽑기"


def 날짜도구(state: 회의상태):
    마지막: AIMessage = state["메시지"][-1]
    답들, 기록 = [], list(state.get("도구기록") or [])
    for c in 마지막.tool_calls:
        if c["name"] == "calc_date":
            결과 = 날짜계산(c["args"].get("expression", ""), c["args"].get("meeting_date", ""))
            기록.append({"표현": c["args"].get("expression"), **결과})
            답들.append(ToolMessage(json.dumps(결과, ensure_ascii=False), tool_call_id=c["id"]))
        else:
            답들.append(ToolMessage("먼저 calc_date 결과를 받은 뒤 submit_tasks 를 다시 부른다.", tool_call_id=c["id"]))
    return {"메시지": 답들, "도구기록": 기록}


def _제출(state: 회의상태) -> list[dict]:
    for msg in reversed(state.get("메시지") or []):
        for c in getattr(msg, "tool_calls", []) or []:
            if c["name"] == "submit_tasks":
                return [{"내용": t.get("content"), "담당자": t.get("owner"), "마감_원문": t.get("due_text"),
                         "마감": t.get("due"), "근거": t.get("evidence") or []} for t in c["args"].get("tasks", [])]
    return []


# ───────────────────────── ③ 검수 (LLM-as-Judge · 네 질문) ─────────────────────────
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
확신이 없으면 false 로 답하고 이유를 적는다."""


def 누락후보(m: meeting.회의, 분류: list[dict], 할일들: list[dict]) -> list[dict]:
    """H14 — 줄 분류는 「할일 · 조건부」 인데 뽑힌 할 일 어느 근거에도 없는 줄을 「할 일 후보」 로 만든다 (LLM 없음).
    덮였는지는 근거 줄과 **글자가 같은지**로만 본다 (앞뒤 줄로 넓히면 옆 줄의 다른 할 일이 가려짐)."""
    덮인줄 = {meeting.줄정리(x) for t in 할일들 for x in t.get("근거") or []}
    후보들 = []
    for x in 분류:
        if x["종류"] in ("할일", "조건부") and 0 < x["번호"] <= len(m.줄들):
            줄 = m.줄들[x["번호"] - 1]
            if meeting.줄정리(줄) not in 덮인줄:
                후보들.append({"내용": f"(할 일 후보 · 뽑기에서 빠짐) {줄.split(': ', 1)[-1]}", "담당자": None,
                             "마감_원문": None, "마감": None, "근거": [줄], "후보": True, "검수": None,
                             "마감_직접씀": False})
    return 후보들


def 검수(state: 회의상태):
    m = meeting.읽기(state["회의id"])
    할일들 = _제출(state)
    if not 할일들:
        return {"할일들": 누락후보(m, state.get("분류") or [], [])}
    목록 = "\n".join(f"[{i + 1}] {json.dumps(t, ensure_ascii=False)}" for i, t in enumerate(할일들))
    _, r = _부르기([SystemMessage(검수지시), HumanMessage(f"{_머리(m)}\n\n회의록:\n{_번호원문(m)}\n\n뽑힌 할 일:\n{목록}")],
                  "검수", m.id, 구조=ReviewResult)
    표 = {x.number: x for x in r.items}
    도구날짜 = {x["날짜"] for x in state.get("도구기록") or [] if x.get("날짜")}
    for i, t in enumerate(할일들):
        # 도구 호출 패턴 확인용: 마감이 있는데 날짜 도구가 돌려준 적 없는 날짜면 LLM 이 직접 쓴 것
        t["마감_직접씀"] = bool(t.get("마감")) and t["마감"] not in 도구날짜
        x = 표.get(i + 1)
        t["검수"] = ({"담당자": x.owner_ok, "마감": x.due_ok, "근거": x.evidence_ok, "확정": x.confirmed, "이유": x.reason}
                   if x else {"담당자": False, "마감": False, "근거": False, "확정": False, "이유": "검수 답이 없음"})
    return {"할일들": 할일들 + 누락후보(m, state.get("분류") or [], 할일들)}


def 나누기(state: 회의상태):
    할일들 = state.get("할일들") or []
    return [Send("가드레일", {"회의id": state["회의id"], "할일": t}) for t in 할일들] or END


# ───────────────────────── ④ 가드레일 (코드 · Send 로 할 일마다) ─────────────────────────
def 가드레일(state: 가드레일입력):
    m = meeting.읽기(state["회의id"])
    t = dict(state["할일"])
    t["걸린규칙"] = 검사(t, m)
    return {"검사결과": [t]}


def 만들기(checkpointer=None):
    g = StateGraph(회의상태)
    g.add_node("분류", 분류)
    g.add_node("뽑기", 뽑기)
    g.add_node("날짜도구", 날짜도구)
    g.add_node("검수", 검수)
    g.add_node("가드레일", 가드레일)
    g.add_edge(START, "분류")
    g.add_conditional_edges("분류", 분류뒤, ["뽑기", END])
    g.add_conditional_edges("뽑기", 뽑기뒤, ["날짜도구", "검수", "뽑기"])
    g.add_edge("날짜도구", "뽑기")
    g.add_conditional_edges("검수", 나누기, ["가드레일", END])
    g.add_edge("가드레일", END)
    return g.compile(checkpointer=checkpointer)
