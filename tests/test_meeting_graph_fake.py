"""그래프 ① v3 배선 시험 — LLM 자리에 정해 둔 가짜 답을 넣어 처음부터 끝까지 도는지 본다 (0원 · 키 불필요).

확인: 분류 → 뽑기 → (calc_date 호출) → 날짜도구 → 뽑기 → (submit_tasks) → 정리 → 대조 → 검수 → Send 가드레일 × 할 일 수 → 끝
- 정리 · C12′: 도구 없이 쓴 날짜 · 마감 표현을 다시 계산한 날짜와 다른 마감
- 대조: 같은 담당자 쌍의 중복만 묻는다 (I15) · 빠진 줄은 묻지 않는다
- H14: 분류가 할 일 · 조건부인데 근거에 없는 줄 → 후보 (코드)
- 검수: 네 질문 · 아니오 하나면 G13 · 후보는 검수에 안 보냄 · 답이 빠진 건은 안전하게 G13
- 걸린규칙에 C13 이 들어감 (v3 기본으로 켬)
실행:  .venv\\Scripts\\python.exe tests\\test_meeting_graph_fake.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import AIMessage  # noqa: E402

from agent import meeting, meeting_graph as mg  # noqa: E402

m1 = meeting.읽기("M1")
줄 = lambda n: m1.줄들[n - 1]  # noqa: E731  (줄 번호 = 회의록 번호)
호출 = []
받은글 = {}


def _t(content, owner, evidence, quote=None, basis="name", due_text=None, due=None, contact="none", contact_quote=None):
    return {"content": content, "owner": owner, "owner_quote": quote, "owner_basis": basis, "due_text": due_text, "due": due,
            "evidence": evidence, "contact": contact, "contact_quote": contact_quote}


tasks = [
    _t("1주차 교안 초안 보내기", "지수", [줄(3), 줄(4)], "지수 씨는", due_text="이번 주 금요일까지", due="2026-10-09"),
    _t("태블릿 10대 빌려주기", "태호", [줄(18)], "태호 씨가"),
    _t("로고 보내기", "지수", [줄(15)], "제가", "self", due="2026-10-04"),                     # 도구 없이 쓴 날짜
    _t("동의서 양식 만들어 영숙 씨께 드리기", "도윤", [줄(8)], "제가", "self",
       due_text="수요일까지", due="2026-10-09", contact="outside", contact_quote="영숙 씨께"),  # 도구 결과(금요일)를 가져다 씀
    _t("홍보 영상 콘티", "민호", [줄(5), 줄(6)], "민호 씨는"),
    _t("콘티 만들기", "민호", [줄(6)], "민호", basis="self"),                                   # 앞 건과 같은 일
]


def 가짜부르기(메시지, 단계, 회의id, 도구=None, 구조=None):
    호출.append(단계)
    받은글[단계] = "\n".join(str(x.content) for x in 메시지)
    if 단계 == "분류":
        # 9 줄(영숙 동의서 인쇄)은 할 일로 분류되지만 뽑기가 빠뜨림 → H14 후보 · 12 줄은 보고로 분류 → 후보 아님
        return None, mg.ClassifyResult(lines=[mg.LineKind(number=i + 1, kind="task" if i + 1 in {3, 4, 9, 18} else
                                                                  "chat" if i + 1 == 19 else "report")
                                              for i in range(len(m1.줄들))])
    if 단계 == "뽑기" and 호출.count("뽑기") == 1:
        return AIMessage("", tool_calls=[{"name": "calc_date", "id": "c1",
                                          "args": {"expression": "이번 주 금요일까지", "meeting_date": "2026-10-05"}}]), None
    if 단계 == "뽑기":
        return AIMessage("", tool_calls=[{"name": "submit_tasks", "id": "s1", "args": {"tasks": tasks}}]), None
    if 단계 == "대조":
        return None, mg.CrossCheckResult(pairs=[
            mg.PairCheck(a=1, b=3, same=False, reason="다른 일"),
            mg.PairCheck(a=5, b=6, same=True, reason="같은 콘티"),
        ])
    if 단계 == "검수":
        좋음 = dict(owner_ok=True, due_ok=True, evidence_ok=True, confirmed=True, reason="")
        return None, mg.ReviewResult(items=[
            mg.ReviewItem(number=1, **좋음),
            mg.ReviewItem(number=2, **{**좋음, "owner_ok": False, "confirmed": False, "reason": "태호는 불참 · 아직 동의 안 함"}),
            mg.ReviewItem(number=3, **{**좋음, "confirmed": False, "reason": "이미 끝난 일"}),
            mg.ReviewItem(number=4, **좋음),
            mg.ReviewItem(number=5, **좋음),
            # 6번은 답을 빼서 「검수 답 없음 → 안전하게 불합격」 을 본다
        ])
    raise AssertionError(단계)


mg._부르기 = 가짜부르기
결과 = mg.만들기().invoke({"회의id": "M1"})
print("호출 순서:", 호출)
for t in 결과["검사결과"]:
    print(f"- {t['내용'][:28]} / {t['담당자']} / {t['마감']} → {t['걸린규칙']}")

assert 호출 == ["분류", "뽑기", "뽑기", "대조", "검수"], 호출
표 = {t["내용"]: t for t in 결과["검사결과"] if not t.get("후보")}
후보 = [t for t in 결과["검사결과"] if t.get("후보")]
걸림 = lambda 내용: set(표[내용]["걸린규칙"])  # noqa: E731

assert 걸림("1주차 교안 초안 보내기") == set() and not 표["1주차 교안 초안 보내기"]["마감_직접씀"]
assert {"A2", "G13", "C13"} <= 걸림("태블릿 10대 빌려주기"), "C13 은 v3 에서 기본으로 켬 (「오늘 못 왔으니까」 의 「오늘」)"
assert {"C10", "C12", "G13"} <= 걸림("로고 보내기") and 표["로고 보내기"]["마감_직접씀"]
# 마감 고치기 — 도구가 돌려준 날짜(10-09)를 가져다 썼지만 근거의 「수요일까지」 를 다시 계산하면 10-07 → 코드가 고침 (v2 에서는 통과했던 모양)
동의서 = 표["동의서 양식 만들어 영숙 씨께 드리기"]
assert 동의서["마감"] == "2026-10-07" and 동의서["마감_LLM"] == "2026-10-09" and 동의서["마감_고침"]
assert 걸림("동의서 양식 만들어 영숙 씨께 드리기") == {"F12"}, "고친 뒤에는 C12 · B4 안 걸림 · 바깥 연락(F12)만"
assert "2026-10-07" in 받은글["검수"], "검수는 코드가 고친 마감을 본다"
assert "I15" in 걸림("콘티 만들기") and "G13" in 걸림("콘티 만들기") and "I15" not in 걸림("홍보 영상 콘티")
assert 표["콘티 만들기"]["검수"] == {"답없음": True, "이유": "검수 답이 없음"}
# 대조는 쌍만 · 검수는 네 질문 · 후보는 검수에 안 감
assert "같은 담당자의 할 일 쌍" in 받은글["대조"] and "근거에 쓰이지 않은 줄" not in 받은글["대조"]
assert "confirmed" in 받은글["검수"] and "할 일 후보" not in 받은글["검수"] and "신호" not in 받은글["검수"]
assert "기준 날짜: 없음" in 받은글["검수"] and "팀: 도윤" in 받은글["검수"]
# H14 — 분류 할일인데 근거에 없는 9 줄만
assert [t["근거"][0] for t in 후보] == [줄(9)] and 후보[0]["걸린규칙"] == ["A1", "H14"] and 후보[0]["후보종류"] == "분류할일"

# 모양이 틀린 뽑기 답 (09-28 v3 측정 첫 회에 실제로 옴: 할 일 한 건이 객체가 아니라 글자) → 멈추지 않고 이어감
import json  # noqa: E402

tasks[:] = [json.dumps(tasks[0], ensure_ascii=False), "엉망인 글자"]
호출.clear()
결과2 = mg.만들기().invoke({"회의id": "M1"})
본2 = [t for t in 결과2["검사결과"] if not t.get("후보")]
assert [t["내용"] for t in 본2] == ["1주차 교안 초안 보내기"], "JSON 글자로 온 항목은 풀어서 씀"
assert 결과2["뽑기경고"] == ["엉망인 글자"], "못 푸는 항목은 버리고 원문을 남김"
assert any(t.get("후보") and t["근거"][0] == 줄(18) for t in 결과2["검사결과"]), "버린 항목의 줄(분류 할일)은 H14 후보로 사람에게"
print("모양이 틀린 뽑기 답: 멈추지 않음 · 경고", 결과2["뽑기경고"])
print("\n=== 배선 시험 통과")
