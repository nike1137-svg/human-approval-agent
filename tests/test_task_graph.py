"""그래프 ② 시험 — 가짜 할 일로, 프로세스를 껐다 켜며 확인한다 (LLM 없음 · 0원).

프로세스 1  할 일 4건 시작: T1 걸림 없음 · T2 A2 · T3 C6 · T4 H14 후보
            → T1 만 자동 등록 · 알림 1 · 대기 3
프로세스 2  (새로 켬) 대기 3건 그대로 → T2 승인 · T3 수정 후 승인 · T4 반려(사유)
            → 등록 3 (자동 · 승인 · 수정 후 승인) · 알림 3 (할 일마다 한 번) · 답 기록 3 · 대기 0
            → 이미 처리한 T2 에 다시 답하면 거절 · 사유 없는 반려는 거절
프로세스 3  T5 를 4일 전에 시작한 것으로 두고 시한 처리 → 자동 반려 + 주최자 알림

실행:  .venv\\Scripts\\python.exe tests\\test_task_graph.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

루트 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(루트))
sys.stdout.reconfigure(encoding="utf-8")

줄 = "도윤: 좋습니다. 지수 씨는 1주차 교안 초안을 이번 주 금요일까지 보내 주세요."
할일들 = {
    "T1": {"내용": "1주차 교안 초안 보내기", "담당자": "지수", "마감": "2026-10-09", "근거": [줄], "걸린규칙": []},
    "T2": {"내용": "태블릿 10대 빌려주기", "담당자": "태호", "마감": None, "근거": [줄], "걸린규칙": ["A2"]},
    "T3": {"내용": "편집본 보내기", "담당자": "민호", "마감": None, "마감_원문": "다음 주쯤", "근거": [줄], "걸린규칙": ["C6"]},
    "T4": {"내용": "(할 일 후보 · 뽑기에서 빠짐) 오늘 날씨 좋네예", "담당자": None, "마감": None, "근거": [줄], "걸린규칙": ["A1", "H14"], "후보": True},
}


def 단계(이름: str):
    from agent import board
    from agent.task_graph import 저장소
    s = 저장소()
    if 이름 == "1":
        for k, t in 할일들.items():
            print(f"  시작 {k} → {s.시작(k, 'M1', '2026-10-05', t)}")
        print("  보드:", [(r["할일id"], r["등록방식"]) for r in board.표("board")])
        print("  알림:", [(r["할일id"], r["받는사람"]) for r in board.표("outbox")])
        print("  대기:", [x["할일id"] for x in s.대기목록()])
        화면 = s.대기목록()[0]
        print("  대기 첫 건 화면 칸:", list(화면.keys()))
        print("  멈춘 이유:", 화면["멈춘 이유"])
        print("  승인하면:", 화면["승인하면 일어나는 일"])
    elif 이름 == "2":
        print("  (새로 켬) 대기:", [x["할일id"] for x in s.대기목록()])
        def 거절되나(시도, *인자, 기대):
            try:
                s.답하기(*인자)
                print(f"  ❌ {시도} 가 받아들여짐")
            except ValueError as e:
                print(("  ✅ " if 기대 in str(e) else "  ❌ ") + f"{시도} 거절: {e}")

        거절되나("대기 중인 T4 를 사유 없이 반려", "T4", "반려", "  ", 기대="사유가 필요")
        print("  T2 →", s.답하기("T2", "승인"))
        print("  T3 →", s.답하기("T3", "수정 후 승인", "마감을 날짜로 정함", 수정={"마감": "2026-10-19"}))
        print("  T4 →", s.답하기("T4", "반려", "할 일이 아님 (잡담)"))
        거절되나("이미 승인한 T2 에 다시 승인", "T2", "승인", 기대="대기 중이 아님")
        print("  보드:", [(r["할일id"], r["등록방식"], r["마감"]) for r in board.표("board")])
        print("  알림:", [(r["할일id"], r["받는사람"]) for r in board.표("outbox")])
        print("  답 기록:", [(r["할일id"], r["결정"], r["사유"]) for r in board.표("decisions")])
        print("  대기:", [x["할일id"] for x in s.대기목록()])
    else:
        옛날 = (datetime.now() - timedelta(days=4)).isoformat(timespec="seconds")
        s.시작("T5", "M1", "2026-10-05", {**할일들["T2"], "내용": "오래 대기한 건"}, 시작시각=옛날)
        print("  시한 처리:", s.시한처리())
        print("  T5 상태:", s.상태("T5"))
        print("  마지막 알림:", [(r["할일id"], r["받는사람"], r["알림"]) for r in board.표("outbox")][-1])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        단계(sys.argv[1])
        sys.exit(0)
    with tempfile.TemporaryDirectory() as d:
        환경 = {**os.environ, "HITL_DATA_DIR": d}
        결과 = {}
        for k in ["1", "2", "3"]:
            print(f"=== 프로세스 {k}")
            r = subprocess.run([sys.executable, __file__, k], capture_output=True, text=True, encoding="utf-8", env=환경, cwd=루트)
            print(r.stdout, end="")
            if r.returncode:
                print(r.stderr)
                raise SystemExit("실패")
            결과[k] = r.stdout
    검사 = [
        ("프로세스 1: T1 만 자동 등록", "보드: [('T1', '자동')]" in 결과["1"]),
        ("프로세스 1: 대기 3건", "대기: ['T2', 'T3', 'T4']" in 결과["1"]),
        ("프로세스 2: 새로 켜도 대기 3건", "(새로 켬) 대기: ['T2', 'T3', 'T4']" in 결과["2"]),
        ("프로세스 2: 등록 3 (자동 · 승인 · 수정 후 승인 · 고친 마감)",
         "보드: [('T1', '자동', '2026-10-09'), ('T2', '승인', None), ('T3', '수정 후 승인', '2026-10-19')]" in 결과["2"]),
        ("프로세스 2: 알림은 할 일마다 한 번 (T1 · T2 · T3)", "알림: [('T1', '지수'), ('T2', '태호'), ('T3', '민호')]" in 결과["2"]),
        ("프로세스 2: 대기 0", "대기: []" in 결과["2"]),
        ("프로세스 2: 다시 답하기 · 사유 없는 반려 거절", 결과["2"].count("✅") == 2 and "❌" not in 결과["2"]),
        ("프로세스 3: 시한 넘긴 건 자동 반려 + 주최자 알림", "T5 상태: 반려" in 결과["3"] and "'도윤'" in 결과["3"]),
    ]
    print("\n=== 판정")
    for 말, ok in 검사:
        print(("  ✅ " if ok else "  ❌ ") + 말)
    sys.exit(0 if all(ok for _, ok in 검사) else 1)
