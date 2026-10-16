# 2026-10-16 22:06 KST
from pathlib import Path

import pytest

from tf.roster import RosterError, RosterRow, parse_roster

DATA = Path(__file__).parent / "data"


def test_parse_tolerates_bom_spaces_blank_lines():
    data = (
        "﻿student_no,name,main_role,sub_roles\n"
        "2026001, 가나다 , 기획자 , 보고서 작성자 ; 발표자\n"
        "2026002,라마바,웹 프로그래머,\n\n"
    ).encode("utf-8")
    rows = parse_roster(data)
    assert rows[0] == RosterRow("2026001", "가나다", "기획자", ("보고서 작성자", "발표자"))
    assert rows[1].sub_roles == ()
    assert len(rows) == 2


def test_parse_rejects_unknown_role():
    with pytest.raises(RosterError, match="역할"):
        parse_roster("student_no,name,main_role,sub_roles\n1,가,요리사,\n".encode("utf-8"))


def test_parse_rejects_missing_column():
    with pytest.raises(RosterError, match="2번째 줄"):
        parse_roster("student_no,name,main_role,sub_roles\n1,가,기획자\n".encode("utf-8"))


def test_parse_rejects_duplicate_student_no():
    with pytest.raises(RosterError, match="학번"):
        parse_roster("student_no,name,main_role,sub_roles\n1,가,기획자,\n1,나,테스터,\n".encode("utf-8"))


def test_parse_rejects_admin_student_no():
    with pytest.raises(RosterError, match="admin"):
        parse_roster("student_no,name,main_role,sub_roles\nadmin,가,기획자,\n".encode("utf-8"))


def test_parse_real_practice_files():
    counts = {name: len(parse_roster((DATA / name).read_bytes())) for name in ["easy.csv", "medium.csv", "hard.csv"]}
    assert counts == {"easy.csv": 8, "medium.csv": 12, "hard.csv": 16}
    hard = parse_roster((DATA / "hard.csv").read_bytes())
    assert hard[6].sub_roles == ("발표자", "테스터")
