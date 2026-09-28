"""회의록 한 편을 그래프 ① 에 실제 LLM 으로 통과시키고 채점한다. 결과 원본은 output/runs/ 에 남긴다.

실행:  .venv\\Scripts\\python.exe -m evaluation.run_one M1
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

from agent import meeting, meeting_graph as mg
from agent.cost import 차단기
from agent.meeting import 루트
from agent.rules import 규칙이름
from evaluation.score import 정답읽기, 채점

sys.stdout.reconfigure(encoding="utf-8")


def 한편(회의id: str, 표시: bool = True) -> dict:
    전 = 차단기.누적()
    결과 = mg.만들기().invoke({"회의id": 회의id})
    든돈 = 차단기.누적() - 전
    m = meeting.읽기(회의id)
    채 = 채점(m, 결과.get("검사결과") or [], 정답읽기()["회의"][회의id])
    기록 = {"회의": 회의id, "때": datetime.now().isoformat(timespec="seconds"), "달러": round(든돈, 6),
            "분류": 결과.get("분류"), "도구기록": 결과.get("도구기록"), "할일": 결과.get("검사결과"),
            "채점": [{"내용": c.할일["내용"], "짝": c.짝, "판정": c.판정, "봐야함": c.봐야함, "걸린규칙": c.걸린규칙} for c in 채.건들],
            "누락": 채.누락}
    폴더 = 루트 / "output" / "runs"
    폴더.mkdir(parents=True, exist_ok=True)
    (폴더 / f"{회의id}_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(기록, ensure_ascii=False, indent=2), encoding="utf-8")
    if 표시:
        print(f"=== {회의id} · 비용 {든돈:.5f}달러 · 누적 {차단기.누적():.5f}달러")
        세기 = {}
        for x in 결과.get("분류") or []:
            세기[x["종류"]] = 세기.get(x["종류"], 0) + 1
        print("줄 분류:", 세기)
        for x in 결과.get("분류") or []:
            print(f"   {x['번호']:>2} [{x['종류']}] {m.줄들[x['번호'] - 1][:46]}")
        print("날짜 도구 호출:", len(결과.get("도구기록") or []), "회")
        for d in 결과.get("도구기록") or []:
            print(f"   「{d['표현']}」 → {d['날짜']}")
        print(f"\n뽑힌 할 일 {len(채.건들)}건 (정답 {len(정답읽기()['회의'][회의id]['할일'])}건)")
        for c in 채.건들:
            t = c.할일
            검 = t.get("검수") or {}
            print(f" - [{c.판정} · 짝 {c.짝} · 봐야함 {'예' if c.봐야함 else '아니오'}] {t['내용']} / {t['담당자']} / "
                  f"{t['마감']}{' (직접 씀)' if t.get('마감_직접씀') else ''}")
            print(f"     걸린 규칙: {', '.join(f'{r} {규칙이름[r]}' for r in c.걸린규칙) or '없음 → 자동 등록'}")
            if 검.get("이유"):
                print(f"     검수: {검['이유']}")
        print("누락 (정답에 있는데 안 뽑힘):", 채.누락 or "없음")
    return 기록


if __name__ == "__main__":
    한편(sys.argv[1] if len(sys.argv) > 1 else "M1")
