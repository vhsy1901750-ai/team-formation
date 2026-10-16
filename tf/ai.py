# 2026-10-16 22:09 KST
"""오픈라우터 AI 배정. 1차, 2차, 3차 모델을 차례로 부르고, 모델마다 전체 120초를 잰다."""
import json
import re
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import requests

from tf.models import AttemptResult, Student
from tf.rules import MAX_TEAM, MIN_TEAM, REQUIRED, validate_plan

URL = "https://openrouter.ai/api/v1/chat/completions"
LIMIT_S = 120.0
MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "poolside/laguna-s-2.1:free",
]


class AIError(Exception):
    def __init__(self, outcome: str, detail: str):
        super().__init__(detail)
        self.outcome = outcome
        self.detail = detail


def _describe(s: Student) -> str:
    subs = ", ".join(s.sub_roles) if s.sub_roles else "없음"
    return f'- 학번 "{s.student_no}", 이름 {s.name}, 주 역할 {s.main_role}, 보조 역할 {subs}'


def build_prompt(teams: dict[int, list[Student]], unassigned: list[Student]) -> str:
    team_lines = []
    for t in sorted(teams):
        members = "\n".join(_describe(m) for m in teams[t]) or "- (팀원 없음)"
        team_lines.append(f"팀{t} (팀 번호 {t}):\n{members}")
    return f"""팀 프로젝트의 팀 배정을 도와줘. 팀이 없는 학생을 지금 있는 팀에 나눠 넣어야 해.

[규칙]
1. 팀이 없는 학생을 한 명도 빠짐없이, 한 학생은 한 팀에만 넣는다.
2. 이미 팀에 있는 학생은 옮기지 않는다. 새 팀을 만들지 않는다.
3. 배정이 끝난 뒤 모든 팀의 인원은 {MIN_TEAM}~{MAX_TEAM}명이다(빈 팀 없음).
4. 한 팀 안에 주 역할이 같은 학생이 2명 이상이면 안 된다.
5. 모든 팀에 {REQUIRED[0]}를 맡을 학생과 {REQUIRED[1]}를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다. 주 역할이나 보조 역할 어느 쪽으로든 맡을 수 있다.

[지금 팀]
{chr(10).join(team_lines)}

[팀이 없는 학생]
{chr(10).join(_describe(s) for s in unassigned)}

[응답 형식]
설명 없이 아래 형식의 JSON 하나만 출력해. team에는 팀 번호(숫자)를 넣어.
{{"assignments": [{{"student_no": "학번", "team": 1}}]}}
"""


def parse_plan(text: str) -> list[tuple[str, int]]:
    """AI 응답에서 배정안을 꺼낸다. 코드 블록이나 앞뒤 설명이 있어도 읽는다."""
    candidates = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data.get("assignments") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        plan = []
        for item in items:
            digits = re.search(r"\d+", str(item.get("team", "")))
            if not digits or "student_no" not in item:
                raise ValueError("assignments 항목에 student_no나 team이 없음")
            plan.append((str(item["student_no"]).strip(), int(digits.group())))
        return plan
    raise ValueError("응답에서 assignments JSON을 찾지 못함")


def call_openrouter(model: str, prompt: str, api_key: str) -> str:
    try:
        resp = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "team-formation"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8000,
                "reasoning": {"effort": "low"},
            },
            timeout=(10, LIMIT_S + 10),
        )
    except requests.RequestException as e:
        raise AIError("오류", f"연결 오류 ({type(e).__name__})") from None
    if resp.status_code != 200:
        raise AIError("오류", f"HTTP {resp.status_code}")
    data = resp.json()
    if "error" in data:
        raise AIError("오류", str(data["error"].get("message", data["error"]))[:200])
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    if not content.strip():
        raise AIError("빈 응답", f"내용이 비어 있음 (finish_reason={choice.get('finish_reason')})")
    return content


def _one_attempt(
    attempt: int,
    model: str,
    call: Callable[[str, str, str], str],
    prompt: str,
    api_key: str,
    limit_s: float,
    on_wait: Callable[[int, str, float], None],
) -> tuple[str | None, AttemptResult]:
    """모델 하나를 부른다. 부른 때부터 응답을 다 받을 때까지 limit_s가 넘으면 버린다."""
    start = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(call, model, prompt, api_key)
    try:
        while True:
            elapsed = time.monotonic() - start
            on_wait(attempt, model, elapsed)
            remaining = limit_s - elapsed
            if remaining <= 0:
                return None, AttemptResult(attempt, model, "시간 초과", f"{limit_s:.0f}초 안에 응답이 끝나지 않음", elapsed)
            try:
                text = future.result(timeout=min(1.0, remaining))
                return text, AttemptResult(attempt, model, "성공", "", time.monotonic() - start)
            except FutureTimeout:
                continue
            except AIError as e:
                return None, AttemptResult(attempt, model, e.outcome, e.detail, time.monotonic() - start)
            except Exception as e:
                return None, AttemptResult(attempt, model, "오류", type(e).__name__, time.monotonic() - start)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def run_ai_assignment(
    teams: dict[int, list[Student]],
    unassigned: list[Student],
    *,
    api_key: str,
    call: Callable[[str, str, str], str] | None = None,
    on_wait: Callable[[int, str, float], None] = lambda *a: None,
    limit_s: float = LIMIT_S,
    models: list[str] | None = None,
) -> tuple[list[tuple[str, int]] | None, list[AttemptResult]]:
    """검사를 통과한 배정안과 시도 기록을 돌려준다. 모두 실패하면 배정안은 None."""
    call = call or sys.modules[__name__].call_openrouter  # 테스트에서 바꿔 끼울 수 있게 부를 때 찾는다
    prompt = build_prompt(teams, unassigned)
    attempts: list[AttemptResult] = []
    for attempt, model in enumerate(models or MODELS, start=1):
        text, result = _one_attempt(attempt, model, call, prompt, api_key, limit_s, on_wait)
        if text is None:
            attempts.append(result)
            continue
        try:
            plan = parse_plan(text)
        except ValueError as e:
            attempts.append(AttemptResult(attempt, model, "형식 오류", str(e), result.elapsed_s))
            continue
        errors = validate_plan(teams, unassigned, plan)
        if errors:
            attempts.append(AttemptResult(attempt, model, "검사 실패", "; ".join(errors[:3]), result.elapsed_s))
            continue
        attempts.append(AttemptResult(attempt, model, "성공", f"{len(plan)}명 배정", result.elapsed_s))
        return plan, attempts
    return None, attempts
