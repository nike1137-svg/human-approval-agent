"""승인 웹 데모 서버 — FastAPI + static/index.html (senior-health-researcher 와 같은 방식).

    .venv\\Scripts\\python.exe app.py      →  브라우저에서 http://127.0.0.1:8520

- **127.0.0.1 로만** 연다 (남이 접속해 API 비용이 나가지 않게 · 전역 규칙 16)
- 「시연 자료로 채우기」 는 data/demo/ 의 그래프 ① 결과를 쓴다 → **키 없이 · 0원**
- 「새로 처리」 만 LLM 을 부른다 (.env 의 OPENAI_API_KEY · 회의록 한 편에 약 0.003달러 (09-28 v3 측정 0.0020~0.0028) · 비용 차단기 상한 5달러)
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import board, meeting, pipeline
from agent.meeting import 루트
from agent.rules import 규칙이름, 묶음, 묶음표
from agent.task_graph import 저장소

app = FastAPI(title="회의록 할 일 승인")
app.mount("/static", StaticFiles(directory=루트 / "static"), name="static")
_잠금 = threading.Lock()
_곳: 저장소 | None = None
# 공개 데모 (DEMO_PUBLIC=1) — 여러 사람이 같은 상태를 보므로 상태를 지우거나 LLM 을 부르는 버튼은 막는다.
# 시연 자료로 채우기 · 승인 · 수정 후 승인 · 반려는 그대로 (눌러 보는 것이 데모)
공개모드 = os.environ.get("DEMO_PUBLIC") == "1"


def _공개면막기():
    if 공개모드:
        raise HTTPException(403, "공개 데모에서는 이 버튼을 쓸 수 없습니다. 내 컴퓨터에서 실행하면 쓸 수 있습니다 (README).")


def _제목(회의id: str) -> str:
    """회의록 파일 첫 줄 「# M1 · 기획 회의」 에서 읽는다 (09-28: 손으로 적은 목록이 M1~M6 만 알아 M8 제목이 비었음)."""
    try:
        return meeting.읽기(회의id).제목
    except FileNotFoundError:
        return ""


def 곳() -> 저장소:
    global _곳
    if _곳 is None:
        _곳 = 저장소()
    return _곳


def _오류문구(e: Exception) -> str:
    """OpenAI 오류를 사람 말로 (루브릭 「오류 없이 실행」 — 화면이 죽지 않고 안내만)."""
    글 = f"{type(e).__name__}: {e}"
    if "insufficient_quota" in 글 or "credit_balance" in 글:
        return "API 잔액이 부족합니다. 키 관리자(퍼실님)에게 충전을 요청하세요. 시연 자료로 채우기는 키 없이 됩니다."
    if "AuthenticationError" in 글 or "api_key" in 글.lower() or "OPENAI_API_KEY" in 글:
        return ".env 에 OPENAI_API_KEY 가 없거나 틀렸습니다. 키 없이 보려면 「시연 자료로 채우기」 를 쓰세요."
    if "예산초과" in 글:
        return f"비용 차단기가 멈췄습니다 — {e}"
    if "Connection" in 글 or "Timeout" in 글:
        return "OpenAI 에 연결하지 못했습니다. 인터넷 연결을 확인하세요."
    return f"처리 중 오류: {글[:300]}"


@app.get("/")
def 첫화면():
    return FileResponse(루트 / "static" / "index.html")


@app.get("/api/config")
def 설정():
    return {"공개": 공개모드}


@app.get("/api/meetings")
def 회의록목록():
    스레드 = board.표("threads")
    대기 = {x["할일id"] for x in 곳().대기목록()}
    목록 = []
    for m in meeting.전부():
        내것 = [r for r in 스레드 if r["회의id"] == m.id]
        목록.append({"id": m.id, "제목": m.제목, "회의일": m.회의일, "참석자": m.참석자, "줄수": len(m.줄들),
                   "작성": "작성자 (실제 말투)" if m.id in ("M5", "M6") else "Claude 초안",
                   "처리됨": bool(내것), "할일수": len(내것), "대기수": sum(r["할일id"] in 대기 for r in 내것),
                   "시연자료": (루트 / "data" / "demo" / f"{m.id}.json").exists()})
    return 목록


@app.get("/api/meetings/{mid}")
def 회의록(mid: str):
    try:
        m = meeting.읽기(mid)
    except FileNotFoundError:
        raise HTTPException(404, "없는 회의록")
    g1 = pipeline.그래프1읽기(mid)
    할일 = []
    if g1:
        for i, t in enumerate(g1.get("검사결과") or [], 1):
            tid = f"{mid}-T{i:02d}"
            할일.append({"할일id": tid, "내용": t.get("내용"), "담당자": t.get("담당자"), "마감": t.get("마감"),
                       "근거줄": (t.get("근거") or [""])[0],
                       "후보": bool(t.get("후보")), "걸린규칙": t.get("걸린규칙") or [], "상태": 곳().상태(tid)})
    return {"id": m.id, "제목": m.제목, "회의일": m.회의일, "참석자": m.참석자, "역할": m.역할, "줄들": m.줄들,
            "진행": g1 and {"분류": g1.get("분류"), "도구기록": g1.get("도구기록"), "할일": 할일}}


@app.post("/api/fill-demo")
def 시연자료로채우기():
    """data/demo/ 의 그래프 ① 결과로 회의록을 모두 채운다 (키 없이 · 0원). 이미 처리한 회의는 건너뜀."""
    한것 = {}
    with _잠금:
        처리된 = {r["회의id"] for r in board.표("threads")}
        for m in meeting.전부():
            p = 루트 / "data" / "demo" / f"{m.id}.json"
            if m.id in 처리된 or not p.exists():
                continue
            한것[m.id] = pipeline.회의처리(m.id, 곳(), json.loads(p.read_text(encoding="utf-8")))
    return {"처리": 한것}


@app.post("/api/process/{mid}")
def 새로처리(mid: str):
    """LLM 으로 회의록 한 편을 새로 처리 (약 0.003달러). 이미 처리한 회의는 다시 하지 않는다."""
    _공개면막기()
    if any(r["회의id"] == mid for r in board.표("threads")):
        raise HTTPException(409, "이미 처리한 회의록입니다. 다시 하려면 「처음 상태로」 를 누르세요.")
    try:
        with _잠금:
            return {"처리": pipeline.회의처리(mid, 곳())}
    except Exception as e:  # noqa: BLE001 — 화면에는 사람 말로
        raise HTTPException(502, _오류문구(e))


@app.get("/api/pending")
def 대기목록():
    지금 = datetime.now()
    목록 = []
    for x in 곳().대기목록():
        분 = int((지금 - datetime.fromisoformat(x["시작시각"])).total_seconds() // 60)
        목록.append({**x, "대기분": 분, "제목": _제목(x["회의id"])})
    return 목록


def _관련건(tid: str, 회의id: str, m: meeting.회의, 근거: set[str]) -> list[dict]:
    """이 건의 근거 줄 · 바로 앞뒤 줄을 근거로 쓴 **같은 회의의 다른 할 일**과 지금 상태 (09-28 사람 처리에서 중복 등록 4쌍 → 화면에 보여 줌)."""
    줄들 = [meeting.줄정리(l) for l in m.줄들]
    번호 = {i for i, l in enumerate(줄들) if l in 근거}
    이웃 = {줄들[j] for i in 번호 for j in (i - 1, i, i + 1) if 0 <= j < len(줄들)}
    관련 = []
    for r in board.표("threads"):
        if r["회의id"] != 회의id or r["할일id"] == tid:
            continue
        t = json.loads(r["할일"] or "{}")
        겹침 = [x for x in t.get("근거") or [] if meeting.줄정리(x) in 이웃]
        if 겹침:
            관련.append({"할일id": r["할일id"], "할 일": t.get("내용"), "담당자": t.get("담당자"), "마감": t.get("마감"),
                       "상태": 곳().상태(r["할일id"]), "겹친 줄": 겹침[0]})
    return 관련


@app.get("/api/pending/{tid}")
def 한건(tid: str):
    for x in 대기목록():
        if x["할일id"] == tid:
            m = meeting.읽기(x["회의id"])
            근거 = {meeting.줄정리(l) for l in x["요청 원문"]}
            x["회의록"] = [{"줄": l, "근거": meeting.줄정리(l) in 근거} for l in m.줄들]
            x["참석자"] = m.참석자
            x["팀"] = meeting.팀
            x["관련 건"] = _관련건(tid, x["회의id"], m, 근거)
            return x
    raise HTTPException(404, "대기 중인 건이 아닙니다 (이미 처리되었을 수 있음)")


@app.post("/api/answer/{tid}")
def 답하기(tid: str, 답: dict = Body(...)):
    try:
        with _잠금:
            상태 = 곳().답하기(tid, 답.get("결정", ""), 답.get("사유", ""), 답.get("수정") or {})
        return {"상태": 상태}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/results")
def 결과():
    보드 = board.표("board")
    원래 = {r["할일id"]: json.loads(r["할일"] or "{}") for r in board.표("threads")}
    for r in 보드:
        r["근거"] = json.loads(r["근거"] or "[]")
        t = 원래.get(r["할일id"], {})
        r["마감_고침"] = bool(t.get("마감_고침"))   # 코드가 고친 마감이면 LLM 이 낸 값도 함께 보임
        r["마감_LLM"] = t.get("마감_LLM")
    답 = board.표("decisions")
    for r in 답:
        r["수정"] = json.loads(r["수정"] or "{}")
    스레드 = board.표("threads")
    대기 = 곳().대기목록()
    # 반려 사유 모음 — 어느 규칙에서 멈춘 건을 사람이 왜 반려했나 (기준을 고칠 재료 · 09-28 작성자 결정: 사유만 남기고 넘기지 않음)
    할일표 = {r["할일id"]: json.loads(r["할일"] or "{}") for r in 스레드}
    반려모음 = [{"할일id": d["할일id"], "할 일": 할일표.get(d["할일id"], {}).get("내용"),
                "멈춘 규칙": 할일표.get(d["할일id"], {}).get("걸린규칙") or [], "사유": d["사유"], "시각": d["시각"]}
               for d in 답 if d["결정"] == "반려"]
    return {"보드": 보드, "알림": board.표("outbox"), "답": 답, "반려모음": 반려모음,
            "세기": {"처리한 할 일": len(스레드), "자동 등록": sum(r["등록방식"] == "자동" for r in 보드),
                   "멈춤": len(스레드) - sum(r["등록방식"] == "자동" for r in 보드), "대기 중": len(대기),
                   "승인": sum(r["결정"] == "승인" for r in 답), "수정 후 승인": sum(r["결정"] == "수정 후 승인" for r in 답),
                   "반려": sum(r["결정"] == "반려" for r in 답)}}


@app.get("/api/rules")
def 규칙표():
    return [{"규칙": r, "뜻": 뜻, "묶음": 묶음(r), "묶음이름": 묶음표[묶음(r)][0], "막으려는 위험": 묶음표[묶음(r)][1]}
            for r, 뜻 in 규칙이름.items()]


@app.post("/api/expire")
def 시한처리():
    _공개면막기()
    with _잠금:
        return {"자동 반려": 곳().시한처리()}


@app.post("/api/reset")
def 처음상태로():
    """시연 데이터(보드 · 알림 · 답 · 체크포인트 · 그래프 ① 결과)를 지운다. 회의록 · 정답 · 비용 장부는 그대로."""
    global _곳
    _공개면막기()
    with _잠금:
        if _곳 is not None:
            _곳.닫기()
            _곳 = None
        폴더 = board.저장폴더()
        try:
            # 체크포인트의 짝 파일(-wal · -shm)도 함께 지운다 — 남으면 새 체크포인트에 옛 기록이 섞일 수 있다
            for 이름 in ["board.sqlite", "checkpoints.sqlite", "checkpoints.sqlite-wal", "checkpoints.sqlite-shm"]:
                (폴더 / 이름).unlink(missing_ok=True)
        except PermissionError:
            raise HTTPException(409, "저장 파일을 다른 프로그램이 쓰고 있어 지우지 못했습니다. 서버를 껐다 켠 뒤 다시 누르세요.")
        shutil.rmtree(폴더 / "graph1", ignore_errors=True)
    return {"지움": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8520)
