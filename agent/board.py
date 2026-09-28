"""업무 보드 · 알림 · 사람의 답 기록 — 실제 업무 시스템 대신 SQLite 로 흉내 낸다 (design.md 1절).

- board     : 등록된 할 일 (= 바깥으로 나간 결과)
- outbox    : 담당자에게 간 알림 (= 되돌릴 수 없는 것)
- decisions : 멈춘 건에 사람이 준 답 (REPORT 4 「멈춘 건을 사람이 어떻게 처리했는지」)
- threads   : 그래프 ② 를 시작한 할 일 목록 (대기 목록을 만들 때 씀)

저장 폴더는 기본 output/, 환경 변수 HITL_DATA_DIR 로 바꿀 수 있다 (시험에서 임시 폴더를 쓰려고).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from agent.meeting import 루트


def 저장폴더() -> Path:
    p = Path(os.environ.get("HITL_DATA_DIR") or 루트 / "output")
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def 연결():
    """쓰고 나면 **반드시 닫는** 연결. sqlite3 의 `with connect() as c` 는 커밋만 하고 닫지 않아서,
    열린 연결이 쌓이면 Windows 에서 「처음 상태로」 가 board.sqlite 를 지우지 못했다 (09-29 새 클론 점검에서 찾음)."""
    c = sqlite3.connect(저장폴더() / "board.sqlite", check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS board (할일id TEXT PRIMARY KEY, 회의id TEXT, 내용 TEXT, 담당자 TEXT, 마감 TEXT,
                                              등록방식 TEXT, 근거 TEXT, 등록시각 TEXT);
            CREATE TABLE IF NOT EXISTS outbox (번호 INTEGER PRIMARY KEY AUTOINCREMENT, 할일id TEXT, 받는사람 TEXT, 알림 TEXT, 시각 TEXT);
            CREATE TABLE IF NOT EXISTS decisions (번호 INTEGER PRIMARY KEY AUTOINCREMENT, 할일id TEXT, 결정 TEXT, 사유 TEXT,
                                                  수정 TEXT, 시각 TEXT);
            CREATE TABLE IF NOT EXISTS threads (할일id TEXT PRIMARY KEY, 회의id TEXT, 시작시각 TEXT, 할일 TEXT);
        """)
        with c:          # 성공하면 커밋 · 오류면 되돌림
            yield c
    finally:
        c.close()


def 지금() -> str:
    return datetime.now().isoformat(timespec="seconds")


def 알림문장(할일: dict) -> str:
    마감 = f"{할일['마감']}까지 " if 할일.get("마감") else ""
    return f"[업무 보드] {마감}{할일.get('내용')}"


def 등록(할일id: str, 회의id: str, 할일: dict, 등록방식: str) -> bool:
    """보드에 올리고 담당자에게 알림. 같은 할일id 가 이미 있으면 아무것도 안 함 (False)."""
    with 연결() as c:
        if c.execute("SELECT 1 FROM board WHERE 할일id=?", (할일id,)).fetchone():
            return False
        c.execute("INSERT INTO board VALUES (?,?,?,?,?,?,?,?)",
                  (할일id, 회의id, 할일.get("내용"), 할일.get("담당자"), 할일.get("마감"), 등록방식,
                   json.dumps(할일.get("근거") or [], ensure_ascii=False), 지금()))
        c.execute("INSERT INTO outbox (할일id, 받는사람, 알림, 시각) VALUES (?,?,?,?)",
                  (할일id, 할일.get("담당자") or "(담당자 없음)", 알림문장(할일), 지금()))
    return True


def 답기록(할일id: str, 결정: str, 사유: str = "", 수정: dict | None = None) -> None:
    with 연결() as c:
        c.execute("INSERT INTO decisions (할일id, 결정, 사유, 수정, 시각) VALUES (?,?,?,?,?)",
                  (할일id, 결정, 사유, json.dumps(수정 or {}, ensure_ascii=False), 지금()))


def 알림보내기(할일id: str, 받는사람: str, 알림: str) -> None:
    with 연결() as c:
        c.execute("INSERT INTO outbox (할일id, 받는사람, 알림, 시각) VALUES (?,?,?,?)", (할일id, 받는사람, 알림, 지금()))


def 스레드기록(할일id: str, 회의id: str, 할일: dict, 시작시각: str | None = None) -> None:
    with 연결() as c:
        c.execute("INSERT OR IGNORE INTO threads VALUES (?,?,?,?)",
                  (할일id, 회의id, 시작시각 or 지금(), json.dumps(할일, ensure_ascii=False)))


def 표(이름: str) -> list[dict]:
    with 연결() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM {이름}")]
