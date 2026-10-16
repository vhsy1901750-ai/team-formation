# 2026-10-16 22:21 KST
"""공고 부록의 연습용 시나리오 3개를 화면 key로 실행한다. 실제 Supabase를 쓴다.

채점 프로그램처럼 학생마다 세션을 따로 열고, 동작마다 result의 첫 단어를 확인한다.
AI 호출은 실패하는 가짜로 바꿔 끼워, 3차 모델까지 실패했을 때 앱이 직접 배정하는 길을 시험한다.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tf import ai, db
from tf.config import get_secret, load_local_env
from tf.rules import team_violations

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).parent / "data"
ADMIN = "admin"


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    def fail(model, prompt, api_key):
        raise ai.AIError("오류", "HTTP 429 (테스트용 가짜)")

    monkeypatch.setattr(ai, "call_openrouter", fail)


class Browser:
    def __init__(self, student_no: str, password: str = "1234"):
        self.at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120)
        self.at.run()
        self.at.text_input(key="login_student_no").input(student_no)
        self.at.text_input(key="login_password").input(password)
        self.at.button(key="login_submit").click().run()
        assert self.at.get_by_key("whoami") is not None, f"{student_no} 로그인 실패"

    def text(self, key: str) -> str:
        return " ".join(m.value for m in self.at.get_by_key(key).markdown)

    def click(self, key: str) -> str:
        self.at.run()  # 다른 사람의 변경을 반영 (자동 새로 고침 대신)
        try:
            button = self.at.button(key=key)
        except Exception:
            return "없음"
        if button.disabled:
            return "막힘"
        button.click().run()
        return self.text("result")


class Scenario:
    def __init__(self):
        load_local_env()
        self.browsers: dict[str, Browser] = {}

    def who(self, student_no: str) -> Browser:
        if student_no not in self.browsers:
            password = get_secret("ADMIN_PASSWORD") if student_no == ADMIN else "1234"
            self.browsers[student_no] = Browser(student_no, password)
        return self.browsers[student_no]

    def start(self, csv_name: str, team_count: int, content: bytes | None = None) -> None:
        admin = self.who(ADMIN)
        content = content if content is not None else (DATA / csv_name).read_bytes()
        admin.at.get_by_key("admin_roster_file").upload(csv_name, content, "text/csv").run()
        admin.at.number_input(key="admin_team_count").set_value(team_count).run()
        assert admin.click("admin_start").startswith("승인")

    def run(self, steps: list[tuple[str, str, str]]) -> None:
        for i, (who, key, expected) in enumerate(steps, start=1):
            got = self.who(who).click(key)
            assert got.split(":")[0] == expected, f"{i}번째 동작 {who} {key}: 기대 {expected}, 실제 {got}"

    def assert_final_teams_valid(self) -> None:
        pool = db.make_pool(get_secret("DATABASE_URL"))
        try:
            state = db.load_state(pool)
        finally:
            pool.close()
        assert state.unassigned == []
        for t, members in state.teams.items():
            assert team_violations(t, members) == [], f"팀{t}: {team_violations(t, members)}"


def no(prefix: str, n: int) -> str:
    return f"{prefix}{n:02d}"


def test_easy_scenario():
    e = lambda n: no("20261", n)  # noqa: E731
    sc = Scenario()
    sc.start("easy.csv", 3)
    sc.run([
        (e(1), "apply_1", "승인"), (e(2), "apply_2", "승인"), (e(3), "apply_3", "승인"),
        (e(4), "apply_1", "대기"), (e(1), f"vote_yes_{e(4)}", "승인"),
        (e(5), "apply_2", "대기"), (e(2), f"vote_yes_{e(5)}", "승인"),
        (e(7), "apply_1", "대기"), (e(1), f"vote_yes_{e(7)}", "대기"), (e(4), f"vote_no_{e(7)}", "거절"),
        (e(6), "apply_3", "대기"), (e(3), f"vote_yes_{e(6)}", "승인"),
        (ADMIN, "admin_close", "승인"), (ADMIN, "admin_assign", "승인"), (ADMIN, "admin_confirm", "승인"),
    ])
    sc.assert_final_teams_valid()


def test_medium_scenario():
    m = lambda n: no("20262", n)  # noqa: E731
    sc = Scenario()
    sc.start("medium.csv", 4)
    sc.run([
        (m(1), "apply_1", "승인"),
        (m(5), "apply_1", "대기"), (m(1), f"vote_yes_{m(5)}", "승인"),
        (m(2), "apply_1", "막힘"),
        (m(6), "apply_2", "승인"),
        (m(9), "apply_2", "대기"), (m(6), f"vote_yes_{m(9)}", "승인"),
        (m(10), "apply_2", "대기"), (m(6), f"vote_yes_{m(10)}", "대기"), (m(9), f"vote_no_{m(10)}", "거절"),
        (m(3), "apply_3", "승인"), (m(11), "apply_4", "승인"),
        (m(12), "apply_4", "대기"), (m(12), "apply_3", "막힘"),
        (ADMIN, "admin_close", "승인"),
        (m(2), "apply_3", "막힘"),
    ])
    unassigned = sc.who(ADMIN).text("unassigned")
    assert "학생3(PL;RW)" in unassigned and "학생11(RW)" in unassigned and "학생12(PT;RW;FD)" in unassigned
    sc.run([(ADMIN, "admin_assign", "승인"), (ADMIN, "admin_confirm", "승인")])
    sc.assert_final_teams_valid()


def test_hard_scenario():
    h = lambda n: no("20263", n)  # noqa: E731
    sc = Scenario()
    sc.start("hard.csv", 4)
    sc.run([
        (h(1), "apply_1", "승인"),
        (h(4), "apply_1", "대기"), (h(1), f"vote_yes_{h(4)}", "승인"),
        (h(7), "apply_1", "대기"), (h(1), f"vote_yes_{h(7)}", "대기"), (h(4), f"vote_yes_{h(7)}", "승인"),
        (h(2), "apply_2", "승인"),
        (h(8), "apply_2", "대기"), (h(2), f"vote_yes_{h(8)}", "승인"),
        (h(5), "apply_2", "대기"), (h(6), "apply_2", "대기"),
        (h(2), f"vote_yes_{h(5)}", "대기"), (h(8), f"vote_yes_{h(5)}", "승인"),
        (h(2), f"vote_yes_{h(6)}", "대기"), (h(8), f"vote_yes_{h(6)}", "대기"), (h(5), f"vote_yes_{h(6)}", "거절"),
        (h(11), "apply_3", "승인"),
        (h(15), "apply_3", "대기"), (h(11), f"vote_yes_{h(15)}", "승인"),
        (h(14), "apply_3", "막힘"),
        (h(10), "apply_4", "승인"),
        (h(13), "apply_1", "대기"), (h(1), f"vote_yes_{h(13)}", "대기"),
        (ADMIN, "admin_close", "승인"),
    ])
    assert "필수 포함 역할" in sc.who(h(14)).text("result")
    assert "학생10(TT;RW)" in sc.who(ADMIN).text("unassigned")
    sc.run([(ADMIN, "admin_assign", "승인")])
    status = sc.who(ADMIN).text("assign_status")
    assert "앱이 직접 배정" in status and "3차 모델" in status
    sc.run([(ADMIN, "admin_confirm", "승인")])
    sc.assert_final_teams_valid()


def test_infeasible_assignment_shows_reason():
    # 학생 2명으로 팀 3개를 채울 수 없으므로 AI를 부르지 않고 이유를 보여 준다
    tiny = "student_no,name,main_role,sub_roles\n9001,가상1,기획자,\n9002,가상2,테스터,\n".encode()
    sc = Scenario()
    sc.start("tiny.csv", 3, content=tiny)
    sc.run([(ADMIN, "admin_close", "승인"), (ADMIN, "admin_assign", "막힘")])
    assert "규칙을 지키는 배정이 없음" in sc.who(ADMIN).text("assign_status")
