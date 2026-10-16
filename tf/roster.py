# 2026-10-16 22:06 KST
"""명단 CSV 읽기. 나눠 주는 파일은 BOM이 붙은 UTF-8이라 utf-8-sig로 읽는다."""
import csv
import io
from dataclasses import dataclass

from tf.rules import ROLES

HEADER = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(Exception):
    pass


@dataclass(frozen=True)
class RosterRow:
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...]


def _check_role(role: str, line: int) -> None:
    if role not in ROLES:
        raise RosterError(f"{line}번째 줄: 역할 '{role}'는 6개 역할에 없음")


def parse_roster(data: bytes) -> list[RosterRow]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("UTF-8 파일이 아님") from None

    rows: list[RosterRow] = []
    seen: set[str] = set()
    for line, cells in enumerate(csv.reader(io.StringIO(text)), start=1):
        cells = [c.strip() for c in cells]
        if not any(cells):
            continue
        if line == 1:
            if cells != HEADER:
                raise RosterError("첫 줄은 student_no,name,main_role,sub_roles 여야 함")
            continue
        if len(cells) != 4:
            raise RosterError(f"{line}번째 줄: 열이 {len(cells)}개임 (4개여야 함)")
        student_no, name, main_role, subs = cells
        if not student_no or not name:
            raise RosterError(f"{line}번째 줄: 학번이나 이름이 비어 있음")
        if student_no == "admin":
            raise RosterError(f"{line}번째 줄: 학번 admin은 관리자용이라 쓸 수 없음")
        if student_no in seen:
            raise RosterError(f"{line}번째 줄: 학번이 앞줄과 겹침 ({student_no})")
        seen.add(student_no)
        _check_role(main_role, line)
        sub_roles = tuple(r.strip() for r in subs.split(";") if r.strip())
        for role in sub_roles:
            _check_role(role, line)
        rows.append(RosterRow(student_no, name, main_role, sub_roles))

    if not rows:
        raise RosterError("학생이 한 명도 없음")
    return rows
