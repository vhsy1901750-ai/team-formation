# 2026-10-16 22:06 KST
"""팀 규칙 판단. DB와 화면을 모르는 순수 함수만 둔다."""
from collections import Counter
from collections.abc import Sequence

from tf.models import Student

ROLES = ("기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자")
PLANNER = "기획자"
WEB = "웹 프로그래머"
REQUIRED = (PLANNER, WEB)
MIN_TEAM = 2
MAX_TEAM = 4

CLOSED = "모집이 마감됨"
HAS_TEAM = "이미 팀이 있음"
HAS_PENDING = "결과를 기다리는 지원이 있음"
FULL = "팀이 꽉 참"
DUP_ROLE = "같은 주 역할의 팀원이 있음"
NO_ROOM_FOR_REQUIRED = "필수 포함 역할을 맡을 학생의 자리가 모자람"


def can_play(s: Student, role: str) -> bool:
    return s.main_role == role or role in s.sub_roles


def covered_required(members: Sequence[Student]) -> int:
    """기획자와 웹 프로그래머를 서로 다른 학생에게 맡길 때 채울 수 있는 역할 수(0~2)."""
    planners = [m for m in members if can_play(m, PLANNER)]
    webs = [m for m in members if can_play(m, WEB)]
    if any(p.student_no != w.student_no for p in planners for w in webs):
        return 2
    return 1 if planners or webs else 0


def missing_required(members: Sequence[Student]) -> list[str]:
    """못 채운 필수 역할 이름. 한 학생만 둘 다 할 수 있으면 웹 프로그래머를 못 채운 것으로 본다."""
    if covered_required(members) == 2:
        return []
    has_planner = any(can_play(m, PLANNER) for m in members)
    has_web = any(can_play(m, WEB) for m in members)
    if has_planner and has_web:
        return [WEB]
    return [r for r, ok in ((PLANNER, has_planner), (WEB, has_web)) if not ok]


def check_join(applicant: Student, members: Sequence[Student]) -> str | None:
    """정원, 주 역할 중복, 필수 포함 역할 자리를 검사한다. 지원할 때와 승인 직전에 쓴다."""
    if len(members) >= MAX_TEAM:
        return FULL
    if any(m.main_role == applicant.main_role for m in members):
        return DUP_ROLE
    after = [*members, applicant]
    remaining = MAX_TEAM - len(after)
    if remaining < len(REQUIRED) - covered_required(after):
        return NO_ROOM_FOR_REQUIRED
    return None


def check_apply(
    applicant: Student,
    members: Sequence[Student],
    *,
    closed: bool,
    has_team: bool,
    has_pending: bool,
) -> str | None:
    if closed:
        return CLOSED
    if has_team:
        return HAS_TEAM
    if has_pending:
        return HAS_PENDING
    return check_join(applicant, members)


def team_violations(team_no: int, members: Sequence[Student]) -> list[str]:
    """확정할 팀 구성이 어긴 규칙. 지키면 빈 목록."""
    n = len(members)
    if n == 0:
        return [f"팀{team_no}에 팀원이 없음"]
    errors = []
    if not MIN_TEAM <= n <= MAX_TEAM:
        errors.append(f"팀{team_no}의 인원이 {n}명임 (2~4명이어야 함)")
    for role, count in Counter(m.main_role for m in members).items():
        if count > 1:
            errors.append(f"팀{team_no}에 주 역할이 {role}인 학생이 {count}명임")
    for role in missing_required(members):
        errors.append(f"팀{team_no}에 {role}를 맡을 학생이 없음")
    return errors


def validate_plan(
    teams: dict[int, list[Student]],
    unassigned: list[Student],
    plan: list[tuple[str, int]],
) -> list[str]:
    """배정안 검사 다섯 가지. 통과하면 빈 목록."""
    by_no = {s.student_no: s for s in unassigned}
    counts = Counter(no for no, _ in plan)
    errors = []

    missing = [by_no[no].name for no in by_no if no not in counts]
    if missing:
        errors.append("배정되지 않은 학생이 있음: " + ", ".join(missing))
    unknown = [no for no in counts if no not in by_no]
    if unknown:
        errors.append("팀이 없는 학생이 아닌 학번이 있음: " + ", ".join(unknown))
    twice = [no for no, c in counts.items() if c > 1]
    if twice:
        errors.append("한 학생이 여러 팀에 배정됨: " + ", ".join(twice))
    bad_teams = sorted({t for _, t in plan if t not in teams})
    if bad_teams:
        errors.append("없는 팀 번호: " + ", ".join(map(str, bad_teams)))
    if errors:
        return errors

    after = {t: list(m) for t, m in teams.items()}
    for no, t in plan:
        after[t].append(by_no[no])
    for t in sorted(after):
        errors.extend(team_violations(t, after[t]))
    return errors
