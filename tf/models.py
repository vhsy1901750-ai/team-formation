# 2026-10-16 22:06 KST
"""앱 전체에서 쓰는 자료형."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Student:
    id: int
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...]


@dataclass(frozen=True)
class User:
    id: int
    student_no: str
    name: str
    is_admin: bool


@dataclass
class Application:
    id: int
    team_no: int
    applicant: Student
    votes: dict[int, str] = field(default_factory=dict)  # 투표한 팀원 id → "찬성" 또는 "거부"


@dataclass
class Proposal:
    plan: list[tuple[str, int]]  # (학번, 팀 번호)
    source: str
    notes: list[str] = field(default_factory=list)


@dataclass
class State:
    closed: bool
    teams: dict[int, list[Student]]
    unassigned: list[Student]
    pending: list[Application]
    proposal: Proposal | None


@dataclass(frozen=True)
class AttemptResult:
    attempt: int
    model: str
    outcome: str  # 성공, 시간 초과, 오류, 빈 응답, 형식 오류, 검사 실패
    detail: str
    elapsed_s: float
