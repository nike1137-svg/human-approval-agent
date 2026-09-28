"""비용 차단기 — 돈이 나가기 **전에** 막는다.

    차단기.확인()                          # LLM 을 부르기 전. 누적이 상한을 넘었으면 예산초과
    차단기.기록(모델, usage, "뽑기", "M1")  # 부른 뒤. 실제 토큰으로 누적

    python -m agent.cost                   # 지금까지 쓴 금액 보기

장부는 output/cost.jsonl (한 줄 = 호출 한 번). 상한은 5달러 (작성자 · 09-28 에 2 → 5).
상한은 아껴 쓰기 목표가 아니라 **코드가 잘못돼 반복 호출이 폭주할 때 막는 안전장치**다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

루트 = Path(__file__).resolve().parent.parent
장부 = 루트 / "output" / "cost.jsonl"
load_dotenv(루트 / ".env")   # 상한(HITL_BUDGET_USD)을 .env 에 적어도 먹게 — 아래에서 읽기 전에 불러온다

# 1M 토큰당 달러 (표준 요금). 2026-09-28 OpenAI 공식 가격표(developers.openai.com/api/docs/pricing)에서 확인.
# 모델을 바꾸면 여기도 바꿔야 한다 — 표에 없는 모델은 부르기 전에 멈춘다.
가격표 = {"gpt-4o-mini": {"입력": 0.15, "출력": 0.60},
          "gpt-5.6-luna": {"입력": 0.20, "출력": 1.20}}
상한달러 = float(os.environ.get("HITL_BUDGET_USD", "5.0"))


class 예산초과(RuntimeError):
    pass


class 차단기_:
    def 누적(self) -> float:
        if not 장부.exists():
            return 0.0
        return sum(json.loads(l)["달러"] for l in 장부.read_text(encoding="utf-8").splitlines() if l.strip())

    def 확인(self, 모델: str = "gpt-4o-mini") -> None:
        if 모델 not in 가격표:
            raise 예산초과(f"가격표에 없는 모델: {모델} — 비용을 셀 수 없어 부르지 않음")
        쓴돈 = self.누적()
        if 쓴돈 >= 상한달러:
            raise 예산초과(f"누적 {쓴돈:.4f}달러 ≥ 상한 {상한달러}달러 — 호출하지 않음")

    def 기록(self, 모델: str, usage: dict | None, 단계: str, 회의id: str = "") -> float:
        usage = usage or {}
        입력, 출력 = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        값 = 가격표[모델]
        달러 = (입력 * 값["입력"] + 출력 * 값["출력"]) / 1_000_000
        장부.parent.mkdir(exist_ok=True)
        with 장부.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"때": datetime.now().isoformat(timespec="seconds"), "모델": 모델, "단계": 단계,
                                "회의": 회의id, "입력": 입력, "출력": 출력, "달러": round(달러, 6)},
                               ensure_ascii=False) + "\n")
        return 달러


차단기 = 차단기_()

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"누적 {차단기.누적():.4f}달러 / 상한 {상한달러}달러")
