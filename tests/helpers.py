# 2026-10-16 22:06 KST
from tf.models import Student


def s(no: int, main: str, *subs: str) -> Student:
    return Student(id=no, student_no=str(no), name=f"학생{no}", main_role=main, sub_roles=tuple(subs))
