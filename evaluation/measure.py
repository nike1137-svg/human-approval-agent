"""측정 — 회의록을 그래프 ① 에 통과시켜 채점하고 표를 만든다 (단계표 6).

    python -m evaluation.measure                        # v3 로 확정된 회의록 모두 두 회차 측정 + 보고 (약 0.034달러)
    python -m evaluation.measure --회의 M8 --버전 1      # v1 (고치기 전 그래프 · 규칙) 로 골라서 측정
    python -m evaluation.measure --다시채점              # 저장해 둔 원본으로 표만 다시 (0원)

원본 폴더
- v1 (고치기 전): output/measure/회차{n}/M*.json    → agent.rules_v1 로 채점 = 기준선
- v2 (채택 안 함): output/measure_v2/…               → 결과는 design.md 8-7 에 기록 (다시 채점하지 않음)
- v3 (지금):       output/measure_v3/회차{n}/M*.json → agent.rules 로 채점
v1 · v3 를 **같은 채점기**(의도한 멈춤 포함)로 잰다. v3 는 M1~M6 · M8 결과를 보고 고친 판이라 이 표는 「본 자료에서의 결과」 다
(09-28 작성자 결정: 새 회의록 M7 판정은 하지 않고 v3 로 제출 — design.md 8-7).
"""
from __future__ import annotations

import json
import sys

from agent import meeting, rules_v1
from agent.cost import 차단기
from agent.meeting import 루트
from agent.rules import 규칙이름
from evaluation.score import 구성들, 구성들_v1, 비교표, 묶음단독, 요약, 정답읽기, 채점, 하나씩빼기

sys.stdout.reconfigure(encoding="utf-8")
# 3 = v3 LLM 측정 원본 · 4 = 원본에 코드 단계(마감 고치기)만 다시 적용한 최종 (evaluation.reapply · design.md 8-8). 보고는 4 가 있으면 4
폴더들 = {1: 루트 / "output" / "measure", 3: 루트 / "output" / "measure_v3", 4: 루트 / "output" / "measure_v3_final"}
회차들 = [1, 2]


def 회의들() -> list[str]:
    """정답이 **확정된** 회의록 모두 (새 회의록은 작성자가 정답을 확정하면 자동으로 들어온다)."""
    g = 정답읽기()
    return sorted([k for k in g["회의"] if g["확정"].get(k)], key=lambda x: int(x[1:]))


def 측정(대상: list[str], v: int):
    if v == 1:
        from agent import meeting_graph_v1 as mg   # 고치기 전 그래프 (커밋 d121b57 그대로)
    else:
        from agent import meeting_graph as mg
    전 = 차단기.누적()
    for n in 회차들:
        (폴더들[v] / f"회차{n}").mkdir(parents=True, exist_ok=True)
        for mid in 대상:
            r = mg.만들기().invoke({"회의id": mid})
            (폴더들[v] / f"회차{n}" / f"{mid}.json").write_text(json.dumps(
                {"분류": r.get("분류"), "도구기록": r.get("도구기록"), "대조기록": r.get("대조기록"),
                 "뽑기경고": r.get("뽑기경고"), "검사결과": r.get("검사결과")}, ensure_ascii=False, indent=1), encoding="utf-8")
            if r.get("뽑기경고"):
                print(f"  ⚠ {mid} 뽑기 항목 {len(r['뽑기경고'])}건 모양이 틀려 버림 (원본에 남김)", flush=True)
            print(f"  v{v} 회차 {n} {mid} 끝 · 누적 {차단기.누적():.4f}달러", flush=True)
    print(f"측정 비용 {차단기.누적() - 전:.4f}달러")


def 읽기(n: int, mid: str, v: int = 3) -> dict:
    return json.loads((폴더들[v] / f"회차{n}" / f"{mid}.json").read_text(encoding="utf-8"))


def 있나(n: int, mid: str, v: int = 3) -> bool:
    return (폴더들[v] / f"회차{n}" / f"{mid}.json").exists()


def 표찍기(줄들: list[dict], 칸: list[str]):
    print("  | " + " | ".join(칸) + " |")
    for x in 줄들:
        print("  | " + " | ".join(str(x[k]) for k in 칸) + " |")


칸 = ["구성", "전체", "멈춤", "놓침", "누락", "헛멈춤", "의도한 멈춤", "손실"]


def 보고():
    gold = 정답읽기()["회의"]
    v1 = {(n, mid): 채점(meeting.읽기(mid), 읽기(n, mid, 1)["검사결과"] or [], gold[mid], rules_v1.검사)
          for n in 회차들 for mid in 회의들() if 있나(n, mid, 1)}
    판 = 4 if 폴더들[4].exists() else 3
    print(f"(v3 = {'LLM 원본 + 코드 단계 다시 적용 (마감 고치기)' if 판 == 4 else 'LLM 측정 원본'} · {폴더들[판].name})")
    v3 = {(n, mid): 채점(meeting.읽기(mid), 읽기(n, mid, 판)["검사결과"] or [], gold[mid])
          for n in 회차들 for mid in 회의들() if 있나(n, mid, 판)}
    묶음들 = [("M1~M6", [f"M{i}" for i in range(1, 7)]), ("M8 (새 회의록 · v3 는 이 결과도 보고 고침)", ["M8"])]
    for 이름, 대상 in 묶음들:
        print(f"\n### {이름} · 두 회차 합")
        for 판, 표, 구성 in [("v1 고치기 전", v1, 구성들_v1), ("v3", v3, 구성들)]:
            x = [표[(n, m)] for n in 회차들 for m in 대상 if (n, m) in 표]
            print(f"  [{판}]" + ("" if x else " — 원본 없음"))
            if x:
                표찍기(비교표(x, 구성), 칸)
    둘다 = list(v3.values())
    if not 둘다:
        return
    print("\n### v3 하나씩 빼기 (최종 A~I 에서 묶음 하나 뺌 · 전체 · 두 회차 합)")
    표찍기(하나씩빼기(둘다), 칸)
    print("\n### v3 묶음 단독")
    표찍기(묶음단독(둘다), ["묶음", "이름", "잡음", "헛멈춤"])
    for n in 회차들:
        print(f"\n### v3 요약 · 회차 {n}:", 요약([v3[(n, m)] for m in 회의들() if (n, m) in v3]))
    print("\n### v3 최종에서 놓친 건 · 누락 (원문과 함께 — 원인은 사람이 읽고 확정)")
    for (n, mid), r in v3.items():
        for c in r.건들:
            if c.봐야함 and not c.걸린규칙:
                print(f"  [놓침 · 회차 {n}] {mid} {c.짝 or '-'} {c.판정}: {c.할일['내용']} / {c.할일['담당자']} / {c.할일['마감']}")
                for l in c.할일.get("근거") or []:
                    print(f"        근거: {l}")
        for gid in r.누락:
            g = next(x for x in gold[mid]["할일"] if x["id"] == gid)
            print(f"  [누락 · 회차 {n}] {gid} {g['내용']} (정답 봐야함 {'예' if g['봐야함'] else '아니오'}) ← {g['근거'][0]}")
    print("\n### v3 규칙별로 걸린 횟수 (두 회차 합)")
    세기: dict[str, int] = {}
    for r in 둘다:
        for c in r.건들:
            for 규 in c.걸린규칙:
                세기[규] = 세기.get(규, 0) + 1
    for 규, k in sorted(세기.items(), key=lambda x: -x[1]):
        print(f"  {규} {규칙이름[규]}: {k}")


if __name__ == "__main__":
    if "--다시채점" not in sys.argv:
        대상 = sys.argv[sys.argv.index("--회의") + 1].split(",") if "--회의" in sys.argv else 회의들()
        v = int(sys.argv[sys.argv.index("--버전") + 1]) if "--버전" in sys.argv else 3
        측정(대상, v)
    보고()
