"""LangGraph 동작 시험 — 설계(design.md)가 기대는 두 가지를 LLM 없이 직접 확인한다.

시험 1  한 그래프 안에서 Send 로 세 갈래(A · B · C) 중 B 만 interrupt 하면,
        A · C 의 다음 단계(등록)는 B 의 답을 기다리지 않고 실행되나?
        → 실행되지 않으면 「그래프 두 개」 구조가 필요하다는 근거가 된다.

시험 2  할 일 한 건 그래프를 SqliteSaver(파일)로 멈춘 뒤 **다른 프로세스**에서
        Command(resume) 로 이어지나? 이어갈 때 멈춘 단계가 처음부터 다시 실행되나?

실행:  .venv\\Scripts\\python.exe tests\\test_langgraph_behavior.py
"""
from __future__ import annotations

import operator
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

sys.stdout.reconfigure(encoding="utf-8")


# ─────────────────────────── 시험 1 ───────────────────────────
실행기록: list[str] = []  # 노드 몸통이 실제로 몇 번 돌았는지


class 회의상태(TypedDict, total=False):
    건들: list[str]
    결과: Annotated[list[str], operator.add]


class 갈래상태(TypedDict):
    건: str


def 나누기(state: 회의상태):
    return [Send("검사", {"건": x}) for x in state["건들"]]


def 검사(state: 갈래상태):
    건 = state["건"]
    실행기록.append(f"검사 {건}")
    if 건 == "B":
        답 = interrupt({"건": 건, "이유": "기준에 걸림"})
        return Command(update={"결과": [f"{건} 사람 답 {답}"]}, goto=Send("등록", {"건": 건}))
    return Command(update={"결과": [f"{건} 자동"]}, goto=Send("등록", {"건": 건}))


def 등록(state: 갈래상태):
    실행기록.append(f"등록 {state['건']}")
    return {"결과": [f"{state['건']} 등록됨"]}


def 시험1():
    g = StateGraph(회의상태)
    g.add_node("검사", 검사)
    g.add_node("등록", 등록)
    g.add_conditional_edges(START, 나누기, ["검사"])
    g.add_edge("등록", END)
    app = g.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "회의-1"}}

    print("=== 시험 1: 한 그래프 · Send 세 갈래 · B 만 멈춤")
    app.invoke({"건들": ["A", "B", "C"], "결과": []}, cfg)
    s = app.get_state(cfg)
    print("  멈춘 직후 실행기록:", 실행기록)
    print("  멈춘 직후 다음 단계:", s.next)
    print("  멈춘 직후 대기 중인 멈춤 수:", sum(len(t.interrupts) for t in s.tasks))
    print("  멈춘 직후 결과:", s.values.get("결과"))
    등록_전 = [x for x in 실행기록 if x.startswith("등록")]

    app.invoke(Command(resume="승인"), cfg)
    s = app.get_state(cfg)
    print("  재개 뒤 실행기록:", 실행기록)
    print("  재개 뒤 다음 단계:", s.next)
    print("  재개 뒤 결과:", s.values.get("결과"))
    print()
    판정 = "A · C 는 B 를 기다리지 않고 등록됨" if {"등록 A", "등록 C"} <= set(등록_전) else "A · C 의 등록이 B 의 답을 기다림 → 그래프 두 개 필요"
    print("  ▶ 판정:", 판정)
    print("  ▶ 재개 때 검사 B 실행 횟수:", 실행기록.count("검사 B"), "/ 검사 A:", 실행기록.count("검사 A"))
    print()


# ─────────────────────────── 시험 2 ───────────────────────────
class 할일상태(TypedDict, total=False):
    할일: str
    걸림: bool
    답: str
    상태: str


def 할일그래프(db: Path, 기록파일: Path):
    def 남기기(말: str):
        with 기록파일.open("a", encoding="utf-8") as f:
            f.write(말 + "\n")

    def 가드레일(state: 할일상태):
        남기기("가드레일 실행")
        return {"걸림": True}

    def 승인대기(state: 할일상태):
        남기기("승인대기 몸통 시작 (interrupt 앞)")
        답 = interrupt({"할일": state["할일"], "멈춘 이유": "시험"})
        남기기(f"승인대기 interrupt 뒤 — 답 {답}")
        return {"답": 답}

    def 등록(state: 할일상태):
        남기기("등록 실행")
        return {"상태": "등록됨"}

    g = StateGraph(할일상태)
    g.add_node("가드레일", 가드레일)
    g.add_node("승인대기", 승인대기)
    g.add_node("등록", 등록)
    g.add_edge(START, "가드레일")
    g.add_conditional_edges("가드레일", lambda s: "승인대기" if s["걸림"] else "등록", ["승인대기", "등록"])
    g.add_edge("승인대기", "등록")
    g.add_edge("등록", END)
    conn = sqlite3.connect(db, check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn)), conn


def 시험2_단계(단계: str, db: Path, 기록파일: Path):
    app, conn = 할일그래프(db, 기록파일)
    cfg = {"configurable": {"thread_id": "M1-07"}}
    if 단계 == "멈추기":
        app.invoke({"할일": "태블릿 10대 빌려주기"}, cfg)
        print("  [프로세스 1] 멈춘 뒤 다음 단계:", app.get_state(cfg).next)
    else:
        s = app.get_state(cfg)
        print("  [프로세스 2] 새로 켠 뒤 다음 단계:", s.next, "· 저장된 값:", sorted(s.values))
        app.invoke(Command(resume="approve"), cfg)
        s = app.get_state(cfg)
        print("  [프로세스 2] 재개 뒤 다음 단계:", s.next, "· 상태:", s.values.get("상태"), "· 답:", s.values.get("답"))
    conn.close()


def 시험2():
    print("=== 시험 2: SqliteSaver · 프로세스를 껐다 켠 뒤 재개")
    with tempfile.TemporaryDirectory() as d:
        db, 기록파일 = Path(d) / "cp.sqlite", Path(d) / "기록.txt"
        for 단계 in ["멈추기", "이어가기"]:  # 단계마다 따로 프로세스를 띄운다 = 껐다 켜기
            r = subprocess.run([sys.executable, __file__, "--시험2", 단계, str(db), str(기록파일)],
                               capture_output=True, text=True, encoding="utf-8")
            print(r.stdout, end="")
            if r.returncode:
                print(r.stderr)
                raise SystemExit("시험 2 실패")
        기록 = 기록파일.read_text(encoding="utf-8").splitlines()
    print("  실행 기록 (두 프로세스 합):")
    for 줄 in 기록:
        print("   -", 줄)
    print()
    print("  ▶ 승인대기 몸통 시작 횟수:", sum("몸통 시작" in x for x in 기록), "(2 면 「멈춘 단계를 처음부터 다시 실행」 확인)")
    print("  ▶ 가드레일 실행 횟수:", sum("가드레일" in x for x in 기록), "(1 이면 앞 단계는 다시 안 돎)")
    print("  ▶ 등록 실행 횟수:", sum("등록 실행" in x for x in 기록))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--시험2":
        시험2_단계(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        시험1()
        시험2()
