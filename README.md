# 사람이 승인하는 에이전트 — 회의록 할 일 자동 등록

회의록에서 할 일을 뽑아 **업무 보드에 등록하고 담당자에게 알림을 보내는** 자동화입니다.
알림 직전에 위험한 건만 멈추고(LangGraph `interrupt`), 사람의 답(승인 · 수정 후 승인 · 반려)을 받아 **멈춘 곳부터 이어서** 실행합니다.
대기 건은 체크포인터(SQLite)에 남아, 서버를 껐다 켜도 이어서 처리할 수 있습니다.

- 설계 · 기준 · 실행 결과: **[REPORT.md](REPORT.md)**
- 쓴 패턴: 워크플로 · 라우팅(줄 분류) · 그라운딩(근거 줄) · 도구 호출(날짜) · 자동 검수(LLM-as-Judge) · `Send` 병렬 · HITL — 어디에 썼는지는 REPORT 2-1절
- 기술: Python 3.12 · LangGraph · langchain-openai (gpt-4o-mini) · FastAPI · HTML (+ three.js 3D, 선택)

## 1. 설치

Python 3.12 가 필요합니다.

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS · Linux**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

아래 명령은 Windows 기준입니다. macOS · Linux 는 `.venv\Scripts\python.exe` 를 `.venv/bin/python` 으로 바꿔 쓰세요.

## 2. 실행 — API 키 없이

```powershell
.venv\Scripts\python.exe app.py
```

브라우저에서 **http://127.0.0.1:8520** 을 엽니다 (내 컴퓨터에서만 열리게 127.0.0.1 로만 띄웁니다).

1. **① 회의록** → **「시연 자료로 채우기」** — 저장해 둔 그래프 ① 결과(`data/demo/`)로 회의록 7편을 처리합니다. 할 일 76건 → 자동 등록 24 · 승인 대기 52
2. **③ 승인함** — 대기 목록에서 한 건을 열면 멈춘 이유 · 요청 원문 · 에이전트의 판단과 근거 · 승인하면 일어나는 일이 보입니다. **승인 / 수정 후 승인 / 반려(사유)** 를 누르면 그 건만 이어서 실행됩니다
3. **④ 결과** — 업무 보드(자동 · 승인 등록) · 사람의 답 기록 · 반려 사유 모음 · 나간 알림
4. **② 회의실** — 회의록을 골라 **▶ 재생**: 참석자가 들어와 앉고, AI 비서가 할 일 카드를 업무 보드(자동) · 승인함(멈춤)으로 옮기며, 카드마다 근거 줄을 말한 사람 머리 위에 말풍선이 뜹니다. 끝에 사람(도윤)이 승인한 카드를 업무 보드로 옮깁니다. 「진행 기록 자세히」 를 펴면 줄 분류 · 날짜 도구 호출 · 할 일마다 자동/멈춤이 있습니다. 3D 는 three.js 를 인터넷(jsdelivr)에서 받으며, 받지 못하면 진행 기록만 보입니다

처음 상태로 돌리려면 ① 회의록의 **「처음 상태로」** (업무 보드 · 알림 · 답 · 대기 목록을 지웁니다. 회의록 · 정답은 그대로).

## 3. 실행 — API 키로 새로 처리 (선택)

1. `.env.example` 을 `.env` 로 복사하고 `OPENAI_API_KEY=` 뒤에 키를 넣습니다. **`.env` 는 저장소에 올리지 않습니다** (`.gitignore`)
2. `app.py` 를 다시 실행 → ① 회의록에서 처리 전 회의록의 **「새로 처리」** (이미 처리한 회의는 「처음 상태로」 뒤에)

- 회의록 한 편에 30초 안팎 걸립니다 (gpt-4o-mini · 호출 5번 안팎)
- 키가 없거나 잔액이 부족하면 화면에 사람 말로 안내합니다 (화면은 멈추지 않음)

## 4. 시험 (LLM 없음 · 키 없이)

```powershell
.venv\Scripts\python.exe tests\test_langgraph_behavior.py
.venv\Scripts\python.exe tests\test_task_graph.py
.venv\Scripts\python.exe tests\test_meeting_graph_fake.py
.venv\Scripts\python.exe -m evaluation.verify_scorer
.venv\Scripts\python.exe -m evaluation.verify_dates
```

| 시험 | 확인하는 것 |
|---|---|
| `test_langgraph_behavior` | interrupt 뒤 이어가면 멈춘 노드가 첫 줄부터 다시 돈다 · 한 그래프면 멈춘 건이 자동 건까지 막는다 (그래서 그래프 둘) |
| `test_task_graph` | 프로세스를 껐다 켜도 대기 건이 남고 승인 · 수정 후 승인 · 반려로 이어짐 · 사유 없는 반려 거절 · 대기 3일 자동 반려 |
| `test_meeting_graph_fake` | 가짜 LLM 으로 그래프 ① 배선 (분류 → 뽑기 ⇄ 날짜 도구 → 정리 → 대조 → 검수 → 가드레일) |
| `verify_scorer` | 채점기 (정답 그대로 넣으면 전부 정상 · 일부러 만든 오답은 모두 잡힘) · 18규칙이 각각 걸리는지 |
| `verify_dates` | 날짜 도구 65건 (회의록 표현 + LLM 이 실제로 넘긴 표현) |

## 5. REPORT 숫자 다시 내기 (키 없이)

측정 원본이 `output/measure*/` 에 들어 있습니다.

```powershell
.venv\Scripts\python.exe -m evaluation.measure --다시채점
.venv\Scripts\python.exe -m evaluation.reapply
```

- 첫 줄: v1(고치기 전) · v3(제출) 비교표 · 하나씩 빼기 · 묶음 단독 · 놓친 건 원문
- 둘째 줄: 저장된 원본에 코드 단계만 다시 적용한 비교 (H14 좁히기 끔 / 켬)
- 새로 재려면 키를 넣고 `python -m evaluation.measure` (회의록 7편 × 2회)

## 6. 폴더

```
app.py                  웹 데모 (FastAPI · 127.0.0.1:8520)
agent/
  meeting_graph.py      그래프 ① 회의록 한 편 (분류 · 뽑기 · 날짜 도구 · 정리 · 대조 · 검수 · 가드레일)
  task_graph.py         그래프 ② 할 일 한 건 (승인대기 interrupt · 등록 · 반려기록 · SqliteSaver)
  rules.py              멈춤 기준 9묶음 18규칙 (코드) · 마감 고치기
  dates.py              날짜 도구
  pipeline.py board.py  그래프 ① → 할 일마다 그래프 ② · 업무 보드 · 알림 (SQLite)
  cost.py               비용 차단기
  *_v1.py               고치기 전 판 (비교용)
data/meetings/          회의록 7편 · data/gold.json 정답 · data/demo/ 시연 자료 (키 없이 보기)
evaluation/             채점기 · 측정 · 검증
tests/                  LLM 없는 시험
static/                 화면 (index.html · 3D 회의실)
docs/img/               화면 캡처
design.md               설계 기록 (결정과 그 근거 · 날짜순)
```
