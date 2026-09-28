"""그래프 ② 할 일 그래프 — 할 일 한 건에 한 번 (thread_id = 할 일 id). 수업 실습의 R3 환불 그래프와 같은 모양.

    START ─(걸린 규칙 없음)→ 등록 → END
          └(걸린 규칙 있음)→ 승인대기 [interrupt] ─(승인 · 수정 후 승인)→ 등록 → END
                                               └(반려)→ 반려기록 → END

- 「승인대기」 노드에는 interrupt 만 둔다. 알림 · 등록은 「등록」 노드에만 있다.
  (수업: 이어갈 때 멈춘 단계를 첫 줄부터 다시 실행 → 묻기 전에 바깥으로 나가는 동작 금지.
   tests/test_langgraph_behavior.py 시험 2 에서 멈춘 노드 몸통이 두 번 도는 것을 확인)
- interrupt 에 담는 것 = 승인 화면에 보일 다섯 가지 (수업 · 원문 필수 구현 3):
  요청 원문 · 에이전트의 판단 · 근거와 검수 · 멈춘 이유 · 승인하면 일어나는 일
- 체크포인터 = SqliteSaver (저장폴더/checkpoints.sqlite) → 껐다 켜도 대기 건이 남는다
- 대기 시한 규칙: 대기가 3일을 넘기면 자동 반려 + 주최자(도윤)에게 알림. 자동 승인은 하지 않는다 (놓침이 더 비싸서)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent import board
from agent.rules import 규칙이름, 묶음, 묶음표, 비교용규칙, 정책규칙

대기시한 = timedelta(days=3)
주최자 = "도윤"


class 할일상태(TypedDict, total=False):
    할일id: str
    회의id: str
    회의일: str
    할일: dict   # 내용 · 담당자 · 마감_원문 · 마감 · 근거 · 검수 · 걸린규칙 · 후보
    답: dict     # {"결정": "승인" | "수정 후 승인" | "반려", "수정": {...}, "사유": str}
    결과: str


def 승인화면(state: 할일상태) -> dict:
    t = state["할일"]
    담당 = t.get("담당자") or "(담당자 없음)"
    마감 = t.get("마감") or "없음"
    멈춘 = [r for r in t.get("걸린규칙") or [] if r not in 비교용규칙]
    return {
        "할일id": state["할일id"], "회의id": state["회의id"], "회의일": state.get("회의일"),
        "요청 원문": t.get("근거") or [],
        "에이전트의 판단": {"할 일": t.get("내용"), "담당자": t.get("담당자"), "마감": t.get("마감"),
                        "회의록의 마감 표현": t.get("마감_원문"), "할 일 후보(뽑기에서 빠짐)": bool(t.get("후보")),
                        "코드가 고친 마감": ({"LLM 값": t.get("마감_LLM"), "고친 값": t.get("마감")} if t.get("마감_고침") else None),
                        # v2 — 값마다 근거 (없으면 v1 기록)
                        "담당 인용": t.get("담당_인용"), "담당 근거": t.get("담당_근거"),
                        "연락 대상": t.get("연락대상"), "연락 인용": t.get("연락_인용"),
                        "후보 종류": t.get("후보종류"), "대조 이유": t.get("대조_이유"),
                        "같은 일(앞 건)": t.get("중복_앞건"), "중복 이유": t.get("중복_이유")},
        "근거와 검수": t.get("검수"),
        "검수 신호": t.get("신호") or [],
        "인정된 아니오": t.get("검수_인정"),
        "멈춘 이유": [{"규칙": r, "뜻": 규칙이름.get(r, r), "막으려는 위험": 묶음표[묶음(r)][1],
                    "업무 정책": r in 정책규칙} for r in 멈춘],
        "승인하면 일어나는 일": f"업무 보드에 「{t.get('내용')}」 등록 → {담당}에게 알림 「{board.알림문장(t)}」 (마감 {마감}). "
                           "알림은 되돌릴 수 없습니다.",
    }


def 갈림(state: 할일상태) -> str:
    return "승인대기" if state["할일"].get("걸린규칙") else "등록"


def 승인대기(state: 할일상태):
    답 = interrupt(승인화면(state))  # ← 여기서 멈춘다. 이 줄보다 앞에 바깥으로 나가는 동작을 두지 않는다
    return {"답": 답}


def 답뒤(state: 할일상태) -> str:
    return "반려기록" if state["답"].get("결정") == "반려" else "등록"


def 등록(state: 할일상태):
    t = dict(state["할일"])
    답 = state.get("답")
    if 답 is None:
        방식 = "자동"
    else:
        방식 = 답.get("결정", "승인")
        if 방식 == "수정 후 승인":
            t.update({k: v for k, v in (답.get("수정") or {}).items() if k in ("내용", "담당자", "마감")})
        board.답기록(state["할일id"], 방식, 답.get("사유", ""), 답.get("수정"))
    board.등록(state["할일id"], state["회의id"], t, 방식)
    return {"결과": f"{방식} 등록", "할일": t}


def 반려기록(state: 할일상태):
    답 = state["답"]
    board.답기록(state["할일id"], "반려", 답.get("사유", ""))
    if 답.get("주최자알림"):
        board.알림보내기(state["할일id"], 주최자, 답["주최자알림"])
    return {"결과": "반려"}


def 만들기(checkpointer):
    g = StateGraph(할일상태)
    g.add_node("승인대기", 승인대기)
    g.add_node("등록", 등록)
    g.add_node("반려기록", 반려기록)
    g.add_conditional_edges(START, 갈림, ["승인대기", "등록"])
    g.add_conditional_edges("승인대기", 답뒤, ["등록", "반려기록"])
    g.add_edge("등록", END)
    g.add_edge("반려기록", END)
    return g.compile(checkpointer=checkpointer)


# ───────────────────────── 쓰는 쪽 (파이프라인 · 웹 화면) ─────────────────────────
class 저장소:
    """그래프 ② 와 SqliteSaver 를 한 번 열어 두고 쓰는 창구."""

    def __init__(self):
        self.conn = sqlite3.connect(board.저장폴더() / "checkpoints.sqlite", check_same_thread=False)
        self.app = 만들기(SqliteSaver(self.conn))

    def 닫기(self) -> None:
        self.conn.close()

    @staticmethod
    def _cfg(할일id: str) -> dict:
        return {"configurable": {"thread_id": 할일id}}

    def 시작(self, 할일id: str, 회의id: str, 회의일: str, 할일: dict, 시작시각: str | None = None) -> str:
        board.스레드기록(할일id, 회의id, 할일, 시작시각)
        if self.app.get_state(self._cfg(할일id)).values:  # 이미 시작한 건은 다시 시작하지 않음
            return self.상태(할일id)
        self.app.invoke({"할일id": 할일id, "회의id": 회의id, "회의일": 회의일, "할일": 할일}, self._cfg(할일id))
        return self.상태(할일id)

    def 상태(self, 할일id: str) -> str:
        s = self.app.get_state(self._cfg(할일id))
        if s.next == ("승인대기",):
            return "대기"
        return s.values.get("결과", "없음")

    def 대기목록(self) -> list[dict]:
        """다음 단계가 「승인대기」 로 남은 스레드 (수업: 다음 단계가 남아 있으면 대기 중). 오래된 것부터."""
        목록 = []
        for r in sorted(board.표("threads"), key=lambda x: x["시작시각"]):
            s = self.app.get_state(self._cfg(r["할일id"]))
            if s.next == ("승인대기",):
                화면 = s.tasks[0].interrupts[0].value if s.tasks and s.tasks[0].interrupts else 승인화면(s.values)
                목록.append({**화면, "시작시각": r["시작시각"]})
        return 목록

    def 답하기(self, 할일id: str, 결정: str, 사유: str = "", 수정: dict | None = None, **덧) -> str:
        if 결정 not in ("승인", "수정 후 승인", "반려"):
            raise ValueError(f"알 수 없는 결정: {결정}")
        if self.상태(할일id) != "대기":
            raise ValueError(f"{할일id} 는 대기 중이 아님 (이미 처리됨: {self.상태(할일id)})")
        if 결정 == "반려" and not 사유.strip():
            raise ValueError("반려에는 사유가 필요합니다 (나중에 왜 막았는지 추적 · 기준을 고칠 재료)")
        self.app.invoke(Command(resume={"결정": 결정, "사유": 사유, "수정": 수정 or {}, **덧}), self._cfg(할일id))
        return self.상태(할일id)

    def 시한처리(self, 지금: datetime | None = None) -> list[str]:
        """대기가 3일을 넘긴 건 → 자동 반려 + 주최자에게 알림."""
        지금 = 지금 or datetime.now()
        처리 = []
        for x in self.대기목록():
            if 지금 - datetime.fromisoformat(x["시작시각"]) > 대기시한:
                self.답하기(x["할일id"], "반려", "대기 3일 넘김 — 자동 반려",
                          주최자알림=f"[대기 시한] 「{x['에이전트의 판단']['할 일']}」 이 3일 동안 처리되지 않아 자동 반려했습니다. 확인해 주세요.")
                처리.append(x["할일id"])
        return 처리
