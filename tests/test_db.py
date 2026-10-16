# 2026-10-16 22:09 KST
"""실제 Supabase의 tf_ 테이블을 지우고 다시 만드는 테스트. 채점 기간에는 실행하지 않는다."""
from pathlib import Path

import psycopg
import pytest

from tf import db
from tf.models import Proposal
from tf.roster import parse_roster

pytestmark = pytest.mark.db
DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def pool():
    from tf.config import get_secret, load_local_env

    load_local_env()
    p = db.make_pool(get_secret("DATABASE_URL"))
    yield p
    p.close()


def reset(pool, name="hard.csv", teams=4):
    db.reset_with_roster(pool, parse_roster((DATA / name).read_bytes()), teams)


def sid(pool, no):
    with pool.connection() as conn:
        return conn.execute("select id from tf_students where student_no = %s", (no,)).fetchone()[0]


def test_ensure_admin_updates_changed_password(pool):
    db.ensure_admin(pool, "old1")
    db.ensure_admin(pool, "new2")
    assert db.authenticate(pool, "admin", "new2").is_admin
    assert db.authenticate(pool, "admin", "old1") is None


def test_reset_keeps_admin_and_hashes(pool):
    db.ensure_admin(pool, "pw1")
    reset(pool)
    msg = db.reset_with_roster(pool, parse_roster((DATA / "easy.csv").read_bytes()), 3)
    assert msg.startswith("승인")
    assert db.authenticate(pool, "admin", "pw1") is not None
    with pool.connection() as conn:
        hashes = [h for (h,) in conn.execute("select password_hash from tf_students where not is_admin")]
    assert len(hashes) == 8 and all(h.startswith("$2") for h in hashes)
    state = db.load_state(pool)
    assert sorted(state.teams) == [1, 2, 3] and len(state.unassigned) == 8 and not state.closed


def test_login(pool):
    reset(pool)
    user = db.authenticate(pool, "2026301", "1234")
    assert user.name == "학생1(PL;RW)" and not user.is_admin
    assert db.authenticate(pool, "2026301", "9999") is None
    assert db.authenticate(pool, "nobody", "1234") is None


def test_apply_empty_team_approved_then_pending(pool):
    reset(pool)
    assert db.apply(pool, sid(pool, "2026301"), 1) == "승인: 팀1의 팀원이 됨"
    assert db.apply(pool, sid(pool, "2026304"), 1).startswith("대기")
    assert db.apply(pool, sid(pool, "2026304"), 2) == "막힘: 결과를 기다리는 지원이 있음"
    assert db.apply(pool, sid(pool, "2026301"), 2) == "막힘: 이미 팀이 있음"
    assert db.apply(pool, sid(pool, "2026302"), 1) == "막힘: 같은 주 역할의 팀원이 있음"
    state = db.load_state(pool)
    assert [s.student_no for s in state.teams[1]] == ["2026301"]
    assert [a.applicant.student_no for a in state.pending] == ["2026304"]


def test_vote_reject_immediately(pool):
    reset(pool)
    db.apply(pool, sid(pool, "2026301"), 1)
    db.apply(pool, sid(pool, "2026304"), 1)
    assert db.vote(pool, sid(pool, "2026301"), "2026304", True) == "승인: 팀1의 팀원이 됨"
    db.apply(pool, sid(pool, "2026307"), 1)
    assert db.vote(pool, sid(pool, "2026301"), "2026307", True).startswith("대기")
    assert db.vote(pool, sid(pool, "2026304"), "2026307", False) == "거절: 팀원이 거부함"


def test_late_member_must_vote_and_recheck_before_approval(pool):
    reset(pool)
    db.apply(pool, sid(pool, "2026302"), 2)
    db.apply(pool, sid(pool, "2026308"), 2)
    db.vote(pool, sid(pool, "2026302"), "2026308", True)
    assert db.apply(pool, sid(pool, "2026305"), 2).startswith("대기")
    assert db.apply(pool, sid(pool, "2026306"), 2).startswith("대기")
    db.vote(pool, sid(pool, "2026302"), "2026305", True)
    assert db.vote(pool, sid(pool, "2026308"), "2026305", True) == "승인: 팀2의 팀원이 됨"
    db.vote(pool, sid(pool, "2026302"), "2026306", True)
    assert db.vote(pool, sid(pool, "2026308"), "2026306", True).startswith("대기")  # 학생5가 아직 안 함
    assert (
        db.vote(pool, sid(pool, "2026305"), "2026306", True)
        == "거절: 승인 직전 검사에서 같은 주 역할의 팀원이 있음"
    )


def test_vote_twice_and_non_member_blocked(pool):
    reset(pool)
    db.apply(pool, sid(pool, "2026301"), 1)
    db.apply(pool, sid(pool, "2026304"), 1)
    db.apply(pool, sid(pool, "2026302"), 2)
    assert db.vote(pool, sid(pool, "2026302"), "2026304", True) == "막힘: 그 팀의 팀원이 아님"
    db.vote(pool, sid(pool, "2026301"), "2026304", True)
    assert db.vote(pool, sid(pool, "2026301"), "2026304", True) == "승인: 팀1의 팀원이 됨"  # 이미 끝난 지원은 결과를 보여 줌
    db.apply(pool, sid(pool, "2026307"), 1)
    db.vote(pool, sid(pool, "2026301"), "2026307", True)
    assert db.vote(pool, sid(pool, "2026301"), "2026307", True) == "막힘: 이미 투표함"


def test_close_rejects_pending_and_drops_singletons(pool):
    reset(pool)
    db.apply(pool, sid(pool, "2026301"), 1)
    db.apply(pool, sid(pool, "2026304"), 1)
    db.vote(pool, sid(pool, "2026301"), "2026304", True)
    db.apply(pool, sid(pool, "2026310"), 4)
    db.apply(pool, sid(pool, "2026313"), 1)
    assert db.close_recruiting(pool).startswith("승인")
    assert db.close_recruiting(pool) == "막힘: 이미 마감됨"
    state = db.load_state(pool)
    assert state.closed and state.pending == []
    assert state.teams[4] == []
    assert "2026310" in [s.student_no for s in state.unassigned]
    assert db.apply(pool, sid(pool, "2026302"), 2) == "막힘: 모집이 마감됨"


def test_slot_unique_constraint(pool):
    reset(pool)
    with pool.connection() as conn:
        team_id = conn.execute("select id from tf_teams where team_no = 1").fetchone()[0]
        conn.execute("insert into tf_members values (%s, 1, %s)", (team_id, sid(pool, "2026301")))
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute("insert into tf_members values (%s, 1, %s)", (team_id, sid(pool, "2026302")))


def test_confirm_revalidates(pool):
    reset(pool, "easy.csv", 3)
    assert db.confirm_proposal(pool) == "막힘: 확정할 배정안이 없음"
    db.close_recruiting(pool)
    db.save_proposal(pool, Proposal(plan=[("2026101", 1)], source="테스트"))
    assert db.confirm_proposal(pool).startswith("막힘")
    good = [("2026101", 1), ("2026104", 1), ("2026102", 2), ("2026105", 2), ("2026107", 2),
            ("2026103", 3), ("2026106", 3), ("2026108", 1)]
    db.save_proposal(pool, Proposal(plan=good, source="테스트", notes=["메모"]))
    assert db.load_state(pool).proposal.notes == ["메모"]
    assert db.confirm_proposal(pool) == "승인: 배정을 확정함"
    state = db.load_state(pool)
    assert state.unassigned == [] and state.proposal is None
