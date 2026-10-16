# 2026-10-16 22:06 KST
"""앱 전체에서 쓰는 자료형."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    id: int
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...]
