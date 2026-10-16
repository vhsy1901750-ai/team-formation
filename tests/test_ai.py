# 2026-10-16 22:09 KST
import time

import pytest
from helpers import s

from tf.ai import AIError, build_prompt, parse_plan, run_ai_assignment

TEAMS = {1: [s(1, "기획자"), s(2, "웹 프로그래머")], 2: []}
UN = [s(3, "기획자"), s(4, "웹 프로그래머")]
GOOD = '{"assignments": [{"student_no": "3", "team": 2}, {"student_no": "4", "team": 2}]}'
BAD = '{"assignments": [{"student_no": "3", "team": 1}, {"student_no": "4", "team": 1}]}'


def test_parse_plan_accepts_fenced_and_numeric():
    text = '배정안입니다.\n```json\n{"assignments": [{"student_no": 2026303, "team": "3"}]}\n```'
    assert parse_plan(text) == [("2026303", 3)]


def test_parse_plan_accepts_team_name():
    assert parse_plan('{"assignments": [{"student_no": "7", "team": "팀2"}]}') == [("7", 2)]


def test_parse_plan_rejects_garbage():
    with pytest.raises(ValueError):
        parse_plan("죄송합니다")
    with pytest.raises(ValueError):
        parse_plan('{"result": []}')


def test_build_prompt_contains_students_and_format():
    prompt = build_prompt(TEAMS, UN)
    assert "학생3" in prompt and "3" in prompt and '"assignments"' in prompt and "팀2" in prompt


def test_fallback_order_timeout_error_invalid():
    def fake(model, prompt, api_key):
        if model == "m1":
            time.sleep(2)
            return GOOD
        if model == "m2":
            raise AIError("오류", "HTTP 429")
        return BAD

    plan, attempts = run_ai_assignment(TEAMS, UN, api_key="x", call=fake, limit_s=0.5, models=["m1", "m2", "m3"])
    assert plan is None
    assert [a.outcome for a in attempts] == ["시간 초과", "오류", "검사 실패"]
    assert attempts[0].elapsed_s < 1.5
    assert "429" in attempts[1].detail


def test_success_on_second_model():
    def fake(model, prompt, api_key):
        if model == "m1":
            raise AIError("빈 응답", "내용이 비어 있음")
        return GOOD

    plan, attempts = run_ai_assignment(TEAMS, UN, api_key="x", call=fake, models=["m1", "m2", "m3"])
    assert sorted(plan) == [("3", 2), ("4", 2)]
    assert [a.outcome for a in attempts] == ["빈 응답", "성공"]


def test_unreadable_response_is_format_error():
    plan, attempts = run_ai_assignment(TEAMS, UN, api_key="x", call=lambda m, p, k: "모르겠어요", models=["m1"])
    assert plan is None and attempts[0].outcome == "형식 오류"


def test_on_wait_reports_attempt_and_model():
    calls = []

    def fake(model, prompt, api_key):
        time.sleep(0.3)
        return GOOD

    run_ai_assignment(TEAMS, UN, api_key="x", call=fake, models=["m1"], on_wait=lambda *a: calls.append(a))
    assert calls and calls[0][:2] == (1, "m1")
