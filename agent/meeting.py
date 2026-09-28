"""회의록 읽기 — data/meetings/M*.md 를 회의일 · 참석자 · 발언 줄로 나눈다.

형식 (design.md 8절): 머리에 「회의일: YYYY-MM-DD (요일)」 · 「참석자: 이름, 이름」, `---` 아래는 「이름: 말」 한 줄씩.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

루트 = Path(__file__).resolve().parent.parent
회의록폴더 = 루트 / "data" / "meetings"

# 팀 = 바깥 연락(F)을 가르는 기준 (09-28 작성자 「가」 · 수아 · 태호도 팀). 그 밖의 사람 · 기관은 바깥
# (영숙 = 복지관 · 수강생 · 관장님 · 복지관 전산 담당 · 시설팀 · 인쇄소 …)
팀 = ["도윤", "지수", "민호", "수아", "태호"]


def 줄정리(s: str) -> str:
    """근거 줄 비교용 — 앞뒤 공백을 떼고 가운데 공백을 하나로."""
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class 회의:
    id: str
    회의일: str
    참석자: list[str]
    줄들: list[str]  # 「이름: 말」 발언 줄만, 원문 그대로
    역할: str = ""   # 머리의 「(도윤 = 대표 · 강사 / …)」 줄 — 검수 ① 에서 씀
    기준날짜: dict | None = None   # 머리의 「개강 11월 4일(수)」 · 「마지막 수업 12월 9일(수)」 → 날짜 도구가 「개강 날 · 개강 전날」 에 씀
    제목: str = ""                 # 첫 줄 「# M1 · 기획 회의」 의 「기획 회의」 (웹 화면)

    @property
    def 원문(self) -> str:
        return "\n".join(self.줄들)


def 읽기(회의id: str) -> 회의:
    글 = (회의록폴더 / f"{회의id}.md").read_text(encoding="utf-8-sig")
    머리, 본문 = 글.split("\n---", 1)
    회의일 = re.search(r"회의일:\s*(\d{4}-\d{2}-\d{2})", 머리).group(1)
    참석자 = [x.strip() for x in re.search(r"참석자:\s*(.+)", 머리).group(1).split(",")]
    줄들 = [l.strip() for l in 본문.splitlines() if re.match(r"^\S+: \S", l.strip())]
    역할 = (re.search(r"^\((.+=.+)\)\s*$", 머리, re.M) or [None, ""])[1]
    해 = int(회의일[:4])
    기준날짜 = {}
    for 이름 in ["개강", "마지막 수업"]:
        m = re.search(이름 + r"\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", 머리)
        if m:
            기준날짜[이름] = f"{해}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    제목 = (re.search(r"^#\s*\S+\s*·\s*(.+?)\s*$", 머리, re.M) or [None, ""])[1]
    return 회의(회의id, 회의일, 참석자, 줄들, 역할, 기준날짜, 제목)


def 전부() -> list[회의]:
    return [읽기(p.stem) for p in sorted(회의록폴더.glob("M*.md"))]
