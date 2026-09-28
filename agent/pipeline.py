"""파이프라인 — 그래프 ① (회의록 한 편) 결과를 받아 할 일마다 그래프 ② (할 일 한 건)를 따로 시작한다.

    python -m agent.pipeline M1          # 회의록 한 편 처리 → 자동 건은 등록, 걸린 건은 대기 목록으로

할 일 id = 「회의id-T두 자리 번호」 (예: M1-T03). 정답 id(M1-03)와 헷갈리지 않게 T 를 붙인다 (채점은 근거 줄로 짝짓는다).
그래프 ① 결과는 저장폴더/graph1/{회의id}.json 에 남긴다 (웹 화면 ② 회의실이 진행 기록을 보여 줄 때 씀).
"""
from __future__ import annotations

import json
import sys

from agent import board, meeting
from agent.task_graph import 저장소

# 대조가 「할 일 아님」 이라고 본 빠진 줄을 사람에게 보일까 (C-2 남김) 버릴까 (C-1). 측정으로 고른다 (design.md 8-5 R6).
# 고르기 전에는 사람에게 더 많이 보이는 쪽(남김)
할일아님_남김 = True


def 보낼것(검사결과: list[dict], 남김: bool | None = None) -> list[dict]:
    남김 = 할일아님_남김 if 남김 is None else 남김
    return [t for t in 검사결과 or [] if 남김 or t.get("후보종류") != "할일아님"]


def 그래프1저장(회의id: str, 결과: dict) -> None:
    폴더 = board.저장폴더() / "graph1"
    폴더.mkdir(exist_ok=True)
    (폴더 / f"{회의id}.json").write_text(json.dumps(
        {"분류": 결과.get("분류"), "도구기록": 결과.get("도구기록"), "대조기록": 결과.get("대조기록"),
         "뽑기경고": 결과.get("뽑기경고"), "검사결과": 결과.get("검사결과")},
        ensure_ascii=False, indent=1), encoding="utf-8")


def 그래프1읽기(회의id: str) -> dict | None:
    p = board.저장폴더() / "graph1" / f"{회의id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def 회의처리(회의id: str, 곳: 저장소 | None = None, 그래프1결과: dict | None = None) -> list[tuple[str, str]]:
    곳 = 곳 or 저장소()
    m = meeting.읽기(회의id)
    if 그래프1결과 is None:
        from agent import meeting_graph  # LLM 을 쓸 때만 불러온다 (시연 자료로 채울 때는 키가 필요 없음)
        그래프1결과 = meeting_graph.만들기().invoke({"회의id": 회의id})
    그래프1저장(회의id, 그래프1결과)
    처리 = []
    for i, t in enumerate(보낼것(그래프1결과.get("검사결과")), 1):
        할일id = f"{회의id}-T{i:02d}"
        처리.append((할일id, 곳.시작(할일id, 회의id, m.회의일, t)))
    return 처리


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for 할일id, 상태 in 회의처리(sys.argv[1] if len(sys.argv) > 1 else "M1"):
        print(할일id, 상태)
