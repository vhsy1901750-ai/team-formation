# 2026-10-16 22:06 KST
import time

from helpers import s

from tf.rules import validate_plan
from tf.solver import explain_infeasible, find_assignment


def test_find_assignment_uses_sub_roles():
    # 팀3: 테스터, 발표자 두 명뿐. 팀4: 빈 팀. 보조 역할 기획자인 테스터가 있어야 풀림
    teams = {3: [s(11, "테스터", "발표자"), s(15, "발표자")], 4: []}
    un = [s(3, "기획자"), s(6, "웹 프로그래머"), s(9, "프론트엔드 디자이너", "웹 프로그래머"), s(12, "테스터", "기획자")]
    plan = find_assignment(teams, un)
    assert plan is not None and validate_plan(teams, un, plan) == []


def test_find_assignment_none_when_full_team_lacks_wp():
    teams = {1: [s(1, "기획자"), s(2, "테스터"), s(3, "발표자"), s(4, "보고서 작성자")], 2: []}
    un = [s(5, "기획자"), s(6, "웹 프로그래머")]
    assert find_assignment(teams, un) is None
    assert "팀1" in explain_infeasible(teams, un)


def test_explain_infeasible_empty_team():
    teams = {1: [s(1, "기획자"), s(2, "웹 프로그래머")], 2: []}
    assert find_assignment(teams, [s(3, "테스터")]) is None
    assert explain_infeasible(teams, [s(3, "테스터")]) != ""


def test_explain_infeasible_no_candidate_for_team():
    teams = {1: [s(1, "테스터"), s(2, "발표자")], 2: [s(3, "기획자"), s(4, "웹 프로그래머")]}
    un = [s(5, "기획자", "테스터"), s(6, "보고서 작성자")]
    assert find_assignment(teams, un) is None
    assert "팀1" in explain_infeasible(teams, un)


def test_find_assignment_eight_students_four_teams_is_fast():
    teams = {1: [], 2: [], 3: [], 4: []}
    un = [
        s(1, "기획자"), s(2, "기획자"), s(3, "기획자"), s(4, "테스터", "기획자"),
        s(5, "웹 프로그래머"), s(6, "웹 프로그래머"), s(7, "웹 프로그래머"), s(8, "발표자"),
    ]
    start = time.perf_counter()
    plan = find_assignment(teams, un)
    assert time.perf_counter() - start < 1.0
    # 웹 프로그래머를 맡을 사람이 3명뿐이라 4팀은 불가능
    assert plan is None


def test_find_assignment_empty_unassigned_valid_teams():
    teams = {1: [s(1, "기획자"), s(2, "웹 프로그래머")]}
    assert find_assignment(teams, []) == []
