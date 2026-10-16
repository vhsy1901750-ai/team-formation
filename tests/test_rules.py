# 2026-10-16 22:06 KST
from helpers import s

from tf.rules import check_apply, check_join, covered_required, team_violations, validate_plan


def test_covered_required_counts_one_person_once():
    assert covered_required([s(1, "기획자", "웹 프로그래머")]) == 1


def test_covered_required_two_people():
    assert covered_required([s(1, "기획자", "웹 프로그래머"), s(2, "테스터", "기획자")]) == 2
    assert covered_required([s(1, "테스터"), s(2, "발표자")]) == 0


def test_block_when_slots_short_for_required():
    team = [s(1, "테스터"), s(2, "발표자")]
    assert check_join(s(3, "보고서 작성자"), team) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_allow_when_applicant_fills_required():
    team = [s(1, "테스터"), s(2, "발표자")]
    assert check_join(s(3, "보고서 작성자", "기획자"), team) is None


def test_block_order_full_before_duplicate():
    team = [s(1, "기획자"), s(2, "웹 프로그래머"), s(3, "테스터"), s(4, "발표자")]
    assert check_join(s(5, "기획자"), team) == "팀이 꽉 참"


def test_block_duplicate_main_role():
    assert check_join(s(3, "기획자"), [s(1, "기획자"), s(2, "웹 프로그래머")]) == "같은 주 역할의 팀원이 있음"


def test_empty_team_never_blocked_by_required():
    assert check_join(s(1, "발표자"), []) is None


def test_check_apply_order():
    assert check_apply(s(1, "기획자"), [], closed=True, has_team=True, has_pending=True) == "모집이 마감됨"
    assert check_apply(s(1, "기획자"), [], closed=False, has_team=True, has_pending=True) == "이미 팀이 있음"
    assert check_apply(s(1, "기획자"), [], closed=False, has_team=False, has_pending=True) == "결과를 기다리는 지원이 있음"
    assert check_apply(s(1, "기획자"), [], closed=False, has_team=False, has_pending=False) is None


def test_team_violations():
    assert team_violations(1, [s(1, "기획자"), s(2, "웹 프로그래머")]) == []
    assert team_violations(1, [s(1, "기획자")])  # 1명
    assert team_violations(2, [s(1, "기획자"), s(2, "기획자", "웹 프로그래머")])  # 주 역할 중복
    v = team_violations(3, [s(1, "기획자"), s(2, "테스터")])
    assert any("팀3에 웹 프로그래머" in x for x in v)


def test_validate_plan_rejects_unknown_and_assigned():
    teams = {1: [s(1, "기획자"), s(2, "웹 프로그래머")], 2: []}
    un = [s(3, "기획자"), s(4, "웹 프로그래머")]
    assert validate_plan(teams, un, [("3", 2), ("4", 2)]) == []
    assert validate_plan(teams, un, [("3", 2), ("4", 2), ("1", 2)])  # 이미 팀이 있는 학생
    assert validate_plan(teams, un, [("3", 2), ("999", 2)])  # 없는 학번, 4번 빠짐
    assert validate_plan(teams, un, [("3", 2), ("3", 1), ("4", 2)])  # 한 학생 두 팀


def test_validate_plan_rejects_unknown_team():
    teams = {1: [s(1, "기획자"), s(2, "웹 프로그래머")]}
    assert validate_plan(teams, [s(3, "테스터")], [("3", 9)])
