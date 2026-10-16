# 2026-10-16 22:06 KST
"""AI가 3차까지 실패했을 때 앱이 스스로 하는 배정. 모든 경우를 끝까지 따진다."""
from tf.models import Student
from tf.rules import MAX_TEAM, MIN_TEAM, can_play, missing_required, team_violations


def find_assignment(
    teams: dict[int, list[Student]], unassigned: list[Student]
) -> list[tuple[str, int]] | None:
    team_nos = sorted(teams)
    current = {t: list(teams[t]) for t in team_nos}
    plan: list[tuple[str, int]] = []

    def short_of_minimum() -> int:
        return sum(max(0, MIN_TEAM - len(current[t])) for t in team_nos)

    def search(i: int) -> bool:
        if short_of_minimum() > len(unassigned) - i:
            return False
        if i == len(unassigned):
            return all(not team_violations(t, current[t]) for t in team_nos)
        student = unassigned[i]
        for t in team_nos:
            members = current[t]
            if len(members) >= MAX_TEAM or any(m.main_role == student.main_role for m in members):
                continue
            members.append(student)
            plan.append((student.student_no, t))
            if search(i + 1):
                return True
            members.pop()
            plan.pop()
        return False

    return list(plan) if search(0) else None


def explain_infeasible(teams: dict[int, list[Student]], unassigned: list[Student]) -> str:
    """규칙을 지키는 배정이 없을 때 관리자에게 보여 줄 이유."""
    team_count = len(teams)
    total = sum(len(m) for m in teams.values()) + len(unassigned)
    if not MIN_TEAM * team_count <= total <= MAX_TEAM * team_count:
        return f"학생 {total}명으로 팀 {team_count}개를 2~4명씩 채울 수 없음"
    short = sum(max(0, MIN_TEAM - len(m)) for m in teams.values())
    if short > len(unassigned):
        return f"팀이 없는 학생 {len(unassigned)}명으로 인원이 모자란 팀을 채울 수 없음"

    reasons = []
    for t in sorted(teams):
        members = teams[t]
        missing = missing_required(members)
        if not missing:
            continue
        if len(members) >= MAX_TEAM:
            reasons += [f"팀{t}에 {role}를 맡을 학생이 없음" for role in missing]
            continue
        candidates = [s for s in unassigned if all(m.main_role != s.main_role for m in members)]
        reasons += [
            f"팀{t}에 {role}를 맡을 학생이 없음"
            for role in missing
            if not any(can_play(s, role) for s in candidates)
        ]
    if reasons:
        return ", ".join(reasons)
    return "모든 경우를 따져 보았지만 규칙을 지키는 배정이 없음"
