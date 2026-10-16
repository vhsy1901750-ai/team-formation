<!-- 2026-10-16 23:04 KST -->
# 팀 프로젝트 팀 편성 웹 앱

학생들이 팀 프로젝트를 위한 팀을 스스로 편성하는 Streamlit 웹 앱이다. 학생은 팀에 지원하고 팀원은 투표로 받아들일지 정한다. 모집을 마감한 뒤 팀이 없는 학생은 AI가 배정안을 내고, 앱이 그 배정안이 규칙을 지키는지 검사한다. AI가 3차 모델까지 실패하면 앱이 모든 경우를 따져 규칙을 지키는 배정을 직접 찾는다.

<!-- TODO: 작성자 이름을 적는다 (README 작성자 이름은 실제 이름을 써도 됨) -->
작성자: (이름)

## 1. 배포 주소

https://team-formation-2026.streamlit.app

## 2. PRD와 구현 계획의 위치

- PRD: [`docs/PRD.md`](docs/PRD.md)
- 구현 계획: [`docs/구현 계획.md`](docs/구현%20계획.md)
- DB 테이블: [`schema.sql`](schema.sql)

## 3. 고른 해결 방법

3장 표의 기능을 모두 어려운 해결로 만들었다.

| 기능 | 고른 해결 | 만든 방법 | 코드 |
|---|---|---|---|
| 다른 사람의 변경 보기 | 어려운 해결 | 로그인 뒤 화면 본문을 `st.fragment(run_every=3)`으로 감싸 3초마다 바뀐 부분만 다시 그림 | `streamlit_app.py`의 `body` |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결 | 지원 단계에서 "남는 자리 수 < 못 채운 필수 역할 수"이면 막음. 기획자와 웹 프로그래머는 서로 다른 학생으로 셈 | `tf/rules.py`의 `check_join`, `covered_required` |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결 | 그 순간의 팀원 모두가 찬성한 때 정원, 주 역할 중복, 필수 포함 역할 자리를 다시 검사. 투표가 끝난 순서대로 처리됨 | `tf/db.py`의 `vote` |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결 | `tf_members`의 `(team_id, slot_no)` 기본 키와 `student_id` 유일성 제약. 팀 행을 `select ... for update`로 잠근 뒤 검사하고 넣음 | `schema.sql`, `tf/db.py` |
| AI 응답이 늦을 때 | 어려운 해결 | 모델마다 별도 스레드로 부르고, 부른 때부터 응답을 다 받을 때까지 전체 120초를 재서 넘으면 다음 모델로 넘어감 | `tf/ai.py`의 `_one_attempt` |
| 3차 모델까지 실패 | 어려운 해결 | 팀이 없는 학생을 팀에 넣는 모든 경우를 되추적으로 따져 검사 다섯 가지를 통과하는 배정을 찾음. 배정이 없으면 AI를 부르지 않고 이유를 보여 줌 | `tf/solver.py` |
| AI 대기 중 화면 | 어려운 해결 | `assign_status`에 "2차 모델(모델 이름)의 응답을 기다리는 중 (35초)"처럼 몇 차 모델인지와 지난 시간을 1초마다 갱신 | `streamlit_app.py`의 `run_assignment` |
| DB(Supabase)가 일시정지되지 않게 | 어려운 해결 | 깃허브 액션 예약 작업이 매일 09:00(KST)에 DB에 질의하고 `tf_settings`에 시각을 기록 | `.github/workflows/keepalive.yml`, `scripts/keepalive.py` |

## 4. 쓴 모델 3개

<!-- TODO: 낮에 다시 시험해서 실제로 응답하는 모델로 확정한다. 10/16 밤 시험에서는 아래 후보가 모두 실패했다(5항). -->
- 1차: `nvidia/nemotron-3-super-120b-a12b:free`
- 2차: `google/gemma-4-31b-it:free`
- 3차: `poolside/laguna-s-2.1:free`

추론 모델의 빈 응답을 줄이려고 요청에 `reasoning: {"effort": "low"}`와 `max_tokens: 8000`을 준다.

## 5. 오픈라우터 AI 모델 호출 실패 사례

**사례 1: 무료 모델 후보 4개가 모두 실패함 (10/16 밤)**

어려움 시나리오의 마감 직후 상태(팀이 없는 학생 8명)를 후보 모델 4개에 보냈더니 하나도 배정안을 내지 못했다.

| 모델 | 결과 |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | 120초 안에 응답이 끝나지 않아 끊음 |
| `poolside/laguna-s-2.1:free` | 120초 안에 응답이 끝나지 않아 끊음 |
| `google/gemma-4-31b-it:free` | HTTP 429 (사용량이 많다며 거절) |
| `thinkingmachines/inkling:free` | HTTP 403. 이 모델은 오픈라우터에 등록된 에이전트 앱에서만 쓸 수 있다는 응답이라 후보에서 뺌 |

근거: 커밋 `2d37e0a`의 메시지에 이 시험 결과를 남김.

<!-- TODO: 배포한 앱에서 AI 배정을 눌러 실패가 보이는 화면을 캡처해 img/ai-fail.png 로 넣고 아래 줄을 실제 내용으로 고친다.
     assign_status에 "1차 모델 ...: 시간 초과 (120초)" 같은 줄이 보이는 순간을 캡처한다. -->
**사례 2: 배포한 앱에서 1차 모델이 실패해 다음 모델로 넘어감**

(실제로 겪은 내용을 적는다. 예: "1차 모델이 120초 안에 응답하지 않아 2차 모델로 넘어감")

화면: `img/ai-fail.png`

## 6. 클로드가 잘못된 추론이나 답변을 한 사례

**사례 1: Supabase 접속 주소를 찾는 화면을 잘못 안내함 (10/16)**

클로드가 Supabase 프로젝트의 Connect 창에 "Type, Source, Method" 칸이 있으니 Type은 URI, Method는 Session pooler를 고르라고 안내했다. 그런데 실제 Connect 창은 Framework, Server, Direct, ORM, MCP 카드를 고르는 모양으로 바뀌어 있어 그런 칸이 없었다. 화면을 캡처해 보여 주자 클로드가 화면이 바뀐 것을 인정했고, Supabase 문서를 찾아 Direct 카드에서 Session pooler를 고르는 방법과 바로 가는 주소(`?showConnect=true&method=session`)로 다시 안내했다. 그 전에도 조직 만들기 화면의 Type 칸을 Connect 창의 Type 칸으로 잘못 알아들은 일이 있었다.

알아챈 방법: 안내대로 해 보니 화면에 그런 칸이 없어서, 실제 화면을 캡처해 보여 줌.

<!-- TODO: 그때 캡처한 Supabase Connect 창 화면을 img/claude-supabase.png 로 넣는다. -->
화면: `img/claude-supabase.png`

**사례 2: AI 배정 뒤 화면을 다시 그리는 코드가 오류를 냄 (10/16)**

클로드가 AI 배정을 마친 뒤 `st.rerun(scope="fragment")`로 화면의 일부만 다시 그리게 했다. 이 호출은 자동 새로 고침(`run_every`)으로 다시 그릴 때만 쓸 수 있어서, 단추를 눌러 전체가 다시 그려지는 경우 `StreamlitInvalidLayoutContextError`가 났다.

알아챈 방법: 연습용 어려움 시나리오를 자동으로 실행하는 테스트(`tests/test_scenarios.py`)에서 AI 배정 단계가 실패함. `st.rerun()`으로 고친 뒤 테스트가 통과했고, 커밋 `40b6c14`의 메시지에 이 내용을 남김.

## 7. 제출한 앱에서 발견한 문제점과 개선 필요 사항

**문제 1: 다른 팀원의 찬성으로 내 지원이 승인되어도 결과 안내가 "대기"로 남음**

결과 안내(`result`)는 내가 마지막으로 누른 단추의 결과만 보여 준다. 그래서 내가 지원해 "대기: 팀원의 투표를 기다림"이 나온 뒤 다른 팀원이 찬성해 승인되면, 팀 목록에는 "내 팀" 표시가 생기지만 위쪽 안내는 계속 "대기"로 남는다. 학생이 헷갈릴 수 있다.

발견한 단계: 부록 3(어려움)의 2단계. 학생4가 팀1에 지원한 뒤 학생1이 찬성하면, 학생4의 화면에 "내 팀: 팀1"과 "대기: 팀원의 투표를 기다림"이 함께 보임.

개선 방향: 내가 낸 지원의 상태가 바뀌면 결과 안내도 그 상태로 바꿔 보여 준다.

<!-- TODO: 배포한 앱에서 위 단계를 해 보고 학생4의 화면을 캡처해 img/stale-result.png 로 넣는다. -->
화면: `img/stale-result.png`

**문제 2: 무료 모델이 모두 늦으면 AI 배정이 6분 가까이 걸림**

모델마다 120초를 기다리므로 1차, 2차, 3차가 모두 시간 초과이면 앱이 직접 배정할 때까지 약 6분이 걸린다. 진행 안내는 1초마다 바뀌지만 관리자에게는 길다. 5항 사례 1처럼 밤에는 무료 모델이 자주 늦었다.

개선 방향: 세 모델을 동시에 불러 먼저 검사를 통과한 배정안을 쓰거나, 앱이 찾은 배정안을 먼저 보여 주고 AI 결과는 나중에 비교한다.

<!-- TODO: 배포한 앱에서 AI 배정이 오래 걸리는 화면(예: "3차 모델 ... 기다리는 중 (100초)")을 캡처해 img/ai-wait.png 로 넣는다. -->
화면: `img/ai-wait.png`

---

## 내 컴퓨터에서 실행하기

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt pytest
.venv/Scripts/streamlit run streamlit_app.py
```

`.env`에 `OPENROUTER_API_KEY`, `DATABASE_URL`, `ADMIN_PASSWORD`가 있어야 한다(저장소에는 올리지 않음). 값이 있는지는 `python scripts/check_secrets.py`로 확인한다. 값은 출력하지 않고 "있음, 없음"만 보여 준다.

## 테스트

```bash
.venv/Scripts/python -m pytest -m "not db"   # DB 없이 도는 규칙, 배정, CSV, AI 테스트
.venv/Scripts/python -m pytest               # 실제 Supabase로 연습 시나리오 3개까지 (DB를 지우므로 채점 기간에는 실행하지 않음)
```

## 파일 구조

| 파일 | 하는 일 |
|---|---|
| `streamlit_app.py` | 화면 |
| `tf/rules.py` | 팀 규칙 판단 (지원 검사, 필수 포함 역할 계산, 배정안 검사) |
| `tf/solver.py` | 앱이 직접 하는 배정 (되추적) |
| `tf/ai.py` | 오픈라우터 호출, 1~3차 모델 넘어가기 |
| `tf/db.py` | DB 작업 (지원, 투표, 마감, 배정안 확정) |
| `tf/roster.py` | 명단 CSV 읽기 |
| `tf/config.py` | 비밀 값 읽기 |
| `schema.sql` | `tf_` 테이블 |
