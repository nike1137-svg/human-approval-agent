"""저장된 v3 측정 원본에 **코드 단계만** 다시 적용한다 (LLM 을 다시 부르지 않음 · 0원 · design.md 8-8).

    python -m evaluation.reapply            # H14 좁힘 끔 / 켬 비교표 (채택 판단용)
    python -m evaluation.reapply --저장      # 지금 설정(meeting_graph.H14_좁힘)으로 다시 적용한 결과를
                                             #   output/measure_v3_final/ 과 시연 자료 data/demo/ (회차 1) 에 쓴다

다시 적용하는 코드 단계: 정리의 마감 고치기 → H14 할 일 후보 → 가드레일(걸린 규칙).
LLM 단계(분류 · 뽑기 · 대조 · 검수)의 답은 원본 그대로다. 단 원본의 검수는 마감을 고치기 **전** 값을 보고 답했다.
"""
from __future__ import annotations

import json
import sys

from agent import meeting, meeting_graph as mg
from agent.meeting import 루트
from agent.rules import 검사, 검수통과, 마감고치기, 비교용규칙
from evaluation.measure import 구성들, 비교표, 읽기, 회의들, 회차들
from evaluation.score import 정답읽기, 채점

sys.stdout.reconfigure(encoding="utf-8")
최종폴더 = 루트 / "output" / "measure_v3_final"


def 다시적용(원본: dict, m: meeting.회의, 좁힘: bool) -> dict:
    본건 = [마감고치기(t, m) for t in 원본["검사결과"] or [] if not t.get("후보")]
    후보들 = mg.누락후보(m, 원본.get("분류") or [], 본건, 좁힘)
    결과 = []
    for t in 본건 + 후보들:
        t = dict(t)
        t["검수_인정"] = 검수통과(t)[1]
        전부 = 검사(t, m)
        t["걸린규칙"] = [r for r in 전부 if r not in 비교용규칙]
        t["비교규칙"] = [r for r in 전부 if r in 비교용규칙]
        결과.append(t)
    return {**원본, "검사결과": 결과, "코드다시적용": {"마감고치기": True, "H14_좁힘": 좁힘}}


def 비교():
    gold = 정답읽기()["회의"]
    칸 = ["전체", "멈춤", "놓침", "누락", "헛멈춤", "손실"]
    print("| 회차 | H14 좁힘 | " + " | ".join(칸) + " |")
    for n in 회차들:
        for 좁힘 in (False, True):
            표 = [채점(meeting.읽기(mid), 다시적용(읽기(n, mid), meeting.읽기(mid), 좁힘)["검사결과"], gold[mid]) for mid in 회의들()]
            x = next(r for r in 비교표(표, 구성들) if r["구성"].startswith("최종"))
            print(f"| {n} | {'켬' if 좁힘 else '끔'} | " + " | ".join(str(x[k]) for k in 칸) + " |")


def 저장():
    for n in 회차들:
        (최종폴더 / f"회차{n}").mkdir(parents=True, exist_ok=True)
        for mid in 회의들():
            r = 다시적용(읽기(n, mid), meeting.읽기(mid), mg.H14_좁힘)
            (최종폴더 / f"회차{n}" / f"{mid}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
            if n == 1:
                (루트 / "data" / "demo" / f"{mid}.json").write_text(json.dumps(
                    {k: r.get(k) for k in ["분류", "도구기록", "대조기록", "뽑기경고", "검사결과", "코드다시적용"]},
                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {최종폴더} · data/demo (회차 1) · H14 좁힘 {mg.H14_좁힘}")


if __name__ == "__main__":
    저장() if "--저장" in sys.argv else 비교()
