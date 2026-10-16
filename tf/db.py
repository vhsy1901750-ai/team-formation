# 2026-10-16 22:09 KST
"""DB 작업. 함수 하나가 트랜잭션 하나이고, 화면의 result에 그대로 보여 줄 문장을 돌려준다.

팀원 수를 바꾸는 작업은 대상 팀 행을 select ... for update로 잠근 뒤 검사하고 쓴다.
그래도 동시에 들어오면 tf_members의 유일성 제약이 먼저 기록된 학생만 남긴다.
"""
import json

import bcrypt
import psycopg
from psycopg_pool import ConnectionPool

from tf.models import Application, AttemptResult, Proposal, State, Student, User
from tf.roster import RosterRow
from tf.rules import FULL, HAS_PENDING, HAS_TEAM, ROLES, check_apply, check_join, validate_plan

ADMIN_NO = "admin"
STUDENT_PASSWORD = "1234"


def make_pool(url: str) -> ConnectionPool:
    return ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        kwargs={"connect_timeout": 15},
        check=ConnectionPool.check_connection,
        open=True,
    )


def _hash(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def _matches(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------- 로그인 ----------


def ensure_admin(pool: ConnectionPool, password: str) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            "select id, password_hash from tf_students where student_no = %s", (ADMIN_NO,)
        ).fetchone()
        if row is None:
            conn.execute(
                "insert into tf_students (student_no, name, main_role, password_hash, is_admin)"
                " values (%s, '관리자', null, %s, true)",
                (ADMIN_NO, _hash(password)),
            )
        elif not _matches(password, row[1]):
            conn.execute(
                "update tf_students set password_hash = %s, is_admin = true where id = %s",
                (_hash(password), row[0]),
            )


def authenticate(pool: ConnectionPool, student_no: str, password: str) -> User | None:
    with pool.connection() as conn:
        row = conn.execute(
            "select id, student_no, name, password_hash, is_admin from tf_students where student_no = %s",
            (student_no.strip(),),
        ).fetchone()
    if row is None or not _matches(password, row[3]):
        return None
    return User(id=row[0], student_no=row[1], name=row[2], is_admin=row[4])


# ---------- 명단 ----------


def reset_with_roster(pool: ConnectionPool, rows: list[RosterRow], team_count: int) -> str:
    hashes = [_hash(STUDENT_PASSWORD, rounds=10) for _ in rows]
    with pool.connection() as conn:
        conn.execute("select id from tf_teams order by id for update")
        conn.execute("delete from tf_votes")
        conn.execute("delete from tf_applications")
        conn.execute("delete from tf_members")
        conn.execute("delete from tf_students where not is_admin")
        conn.execute("delete from tf_teams")
        conn.execute("delete from tf_settings where key in ('closed', 'proposal')")
        with conn.cursor() as cur:
            cur.executemany(
                "insert into tf_teams (team_no, name) values (%s, %s)",
                [(n, f"팀{n}") for n in range(1, team_count + 1)],
            )
            cur.executemany(
                "insert into tf_students (student_no, name, main_role, password_hash) values (%s, %s, %s, %s)",
                [(r.student_no, r.name, r.main_role, h) for r, h in zip(rows, hashes)],
            )
            ids = dict(conn.execute("select student_no, id from tf_students where not is_admin").fetchall())
            cur.executemany(
                "insert into tf_student_sub_roles (student_id, role) values (%s, %s)",
                [(ids[r.student_no], role) for r in rows for role in r.sub_roles],
            )
    return f"승인: 명단으로 처음 상태를 만듦 (학생 {len(rows)}명, 팀 {team_count}개)"


# ---------- 읽기 ----------


def _students(conn: psycopg.Connection) -> dict[int, Student]:
    rows = conn.execute(
        "select s.id, s.student_no, s.name, s.main_role, array_remove(array_agg(r.role), null)"
        " from tf_students s left join tf_student_sub_roles r on r.student_id = s.id"
        " where not s.is_admin group by s.id order by s.student_no"
    ).fetchall()
    return {
        r[0]: Student(r[0], r[1], r[2], r[3], tuple(sorted(r[4], key=ROLES.index))) for r in rows
    }


def _settings(conn: psycopg.Connection) -> dict[str, str]:
    return dict(conn.execute("select key, value from tf_settings").fetchall())


def _decode_proposal(raw: str | None) -> Proposal | None:
    if not raw:
        return None
    d = json.loads(raw)
    return Proposal(plan=[(str(no), int(t)) for no, t in d["plan"]], source=d["source"], notes=d["notes"])


def _load_state(conn: psycopg.Connection) -> State:
    students = _students(conn)
    teams: dict[int, list[Student]] = {}
    assigned: set[int] = set()
    for team_no, student_id in conn.execute(
        "select t.team_no, m.student_id from tf_teams t left join tf_members m on m.team_id = t.id"
        " order by t.team_no, m.slot_no"
    ):
        teams.setdefault(team_no, [])
        if student_id is not None:
            teams[team_no].append(students[student_id])
            assigned.add(student_id)

    pending: dict[int, Application] = {}
    for app_id, team_no, student_id, voter_id, vote in conn.execute(
        "select a.id, t.team_no, a.student_id, v.voter_id, v.vote from tf_applications a"
        " join tf_teams t on t.id = a.team_id left join tf_votes v on v.application_id = a.id"
        " where a.status = '대기' order by a.id"
    ):
        app = pending.setdefault(app_id, Application(app_id, team_no, students[student_id]))
        if voter_id is not None:
            app.votes[voter_id] = vote

    settings = _settings(conn)
    return State(
        closed=settings.get("closed") == "true",
        teams=teams,
        unassigned=[s for s in students.values() if s.id not in assigned],
        pending=list(pending.values()),
        proposal=_decode_proposal(settings.get("proposal")),
    )


def load_state(pool: ConnectionPool) -> State:
    with pool.connection() as conn:
        return _load_state(conn)


# ---------- 지원과 투표 ----------


def _is_closed(conn: psycopg.Connection) -> bool:
    row = conn.execute("select value from tf_settings where key = 'closed'").fetchone()
    return row is not None and row[0] == "true"


def _set(conn: psycopg.Connection, key: str, value: str) -> None:
    conn.execute(
        "insert into tf_settings (key, value) values (%s, %s)"
        " on conflict (key) do update set value = excluded.value",
        (key, value),
    )


def _team_members(conn: psycopg.Connection, team_id: int, students: dict[int, Student]) -> list[Student]:
    rows = conn.execute(
        "select student_id from tf_members where team_id = %s order by slot_no", (team_id,)
    ).fetchall()
    return [students[r[0]] for r in rows]


def _insert_member(conn: psycopg.Connection, team_id: int, student_id: int) -> None:
    used = {r[0] for r in conn.execute("select slot_no from tf_members where team_id = %s", (team_id,))}
    slot = min(set(range(1, 5)) - used, default=5)  # 5는 check 제약에 걸린다
    conn.execute(
        "insert into tf_members (team_id, slot_no, student_id) values (%s, %s, %s)",
        (team_id, slot, student_id),
    )


def _member_violation(e: psycopg.errors.IntegrityError) -> str:
    """tf_members 제약에 걸린 이유. student_id 제약이면 이미 팀이 있는 것이다."""
    constraint = e.diag.constraint_name or ""
    return HAS_TEAM if "student_id" in constraint else FULL


def apply(pool: ConnectionPool, student_id: int, team_no: int) -> str:
    with pool.connection() as conn:
        team = conn.execute("select id from tf_teams where team_no = %s for update", (team_no,)).fetchone()
        if team is None:
            return "막힘: 없는 팀"
        team_id = team[0]
        students = _students(conn)
        applicant = students[student_id]
        members = _team_members(conn, team_id, students)
        has_team = conn.execute("select 1 from tf_members where student_id = %s", (student_id,)).fetchone()
        has_pending = conn.execute(
            "select 1 from tf_applications where student_id = %s and status = '대기'", (student_id,)
        ).fetchone()
        reason = check_apply(
            applicant,
            members,
            closed=_is_closed(conn),
            has_team=has_team is not None,
            has_pending=has_pending is not None,
        )
        if reason:
            return f"막힘: {reason}"

        if not members:  # 빈 팀은 투표할 팀원이 없으므로 바로 승인
            try:
                with conn.transaction():
                    _insert_member(conn, team_id, student_id)
                    conn.execute(
                        "insert into tf_applications (team_id, student_id, status, decided_at)"
                        " values (%s, %s, '승인', now())",
                        (team_id, student_id),
                    )
            except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation) as e:
                return f"막힘: {_member_violation(e)}"
            return f"승인: 팀{team_no}의 팀원이 됨"

        try:
            with conn.transaction():
                conn.execute(
                    "insert into tf_applications (team_id, student_id, status) values (%s, %s, '대기')",
                    (team_id, student_id),
                )
        except psycopg.errors.UniqueViolation:
            return f"막힘: {HAS_PENDING}"
        return "대기: 팀원의 투표를 기다림"


def _status_text(status: str, reason: str | None, team_no: int) -> str:
    if status == "승인":
        return f"승인: 팀{team_no}의 팀원이 됨"
    if status == "거절":
        return f"거절: {reason}"
    return "대기: 다른 팀원의 투표를 기다림"


def _decide(conn: psycopg.Connection, app_id: int, status: str, reason: str | None) -> None:
    conn.execute(
        "update tf_applications set status = %s, reason = %s, decided_at = now() where id = %s",
        (status, reason, app_id),
    )


def vote(pool: ConnectionPool, voter_id: int, applicant_no: str, yes: bool) -> str:
    with pool.connection() as conn:
        app = conn.execute(
            "select a.id, a.team_id from tf_applications a join tf_students s on s.id = a.student_id"
            " where s.student_no = %s order by a.id desc limit 1",
            (applicant_no,),
        ).fetchone()
        if app is None:
            return "막힘: 지원을 찾을 수 없음"
        app_id, team_id = app
        team_no = conn.execute("select team_no from tf_teams where id = %s for update", (team_id,)).fetchone()[0]
        status, reason, applicant_id = conn.execute(
            "select status, reason, student_id from tf_applications where id = %s", (app_id,)
        ).fetchone()

        if _is_closed(conn):
            return "막힘: 모집이 마감됨"
        if status != "대기":
            return _status_text(status, reason, team_no)
        students = _students(conn)
        members = _team_members(conn, team_id, students)
        if voter_id not in {m.id for m in members}:
            return "막힘: 그 팀의 팀원이 아님"
        try:
            with conn.transaction():
                conn.execute(
                    "insert into tf_votes (application_id, voter_id, vote) values (%s, %s, %s)",
                    (app_id, voter_id, "찬성" if yes else "거부"),
                )
        except psycopg.errors.UniqueViolation:
            return "막힘: 이미 투표함"

        if not yes:
            _decide(conn, app_id, "거절", "팀원이 거부함")
            return "거절: 팀원이 거부함"

        yes_voters = {
            r[0]
            for r in conn.execute(
                "select voter_id from tf_votes where application_id = %s and vote = '찬성'", (app_id,)
            )
        }
        if not all(m.id in yes_voters for m in members):
            return "대기: 다른 팀원의 투표를 기다림"

        # 승인 직전 재검사: 같은 팀의 다른 지원이 먼저 승인되어 팀이 바뀌었을 수 있다
        problem = check_join(students[applicant_id], members)
        if problem:
            _decide(conn, app_id, "거절", f"승인 직전 검사에서 {problem}")
            return f"거절: 승인 직전 검사에서 {problem}"
        try:
            with conn.transaction():
                _insert_member(conn, team_id, applicant_id)
                _decide(conn, app_id, "승인", None)
        except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation) as e:
            problem = _member_violation(e)
            _decide(conn, app_id, "거절", problem)
            return f"거절: {problem}"
        return f"승인: 팀{team_no}의 팀원이 됨"


# ---------- 마감과 배정 ----------


def close_recruiting(pool: ConnectionPool) -> str:
    with pool.connection() as conn:
        conn.execute("select id from tf_teams order by id for update")
        if _is_closed(conn):
            return "막힘: 이미 마감됨"
        rejected = conn.execute(
            "update tf_applications set status = '거절', reason = '모집 마감', decided_at = now()"
            " where status = '대기'"
        ).rowcount
        dropped = conn.execute(
            "delete from tf_members where team_id in"
            " (select team_id from tf_members group by team_id having count(*) = 1)"
        ).rowcount
        _set(conn, "closed", "true")
    return f"승인: 모집을 마감함 (대기 지원 {rejected}건 거절, 혼자인 팀에서 {dropped}명 빠짐)"


def save_proposal(pool: ConnectionPool, proposal: Proposal) -> None:
    raw = json.dumps(
        {"plan": proposal.plan, "source": proposal.source, "notes": proposal.notes}, ensure_ascii=False
    )
    with pool.connection() as conn:
        _set(conn, "proposal", raw)


def confirm_proposal(pool: ConnectionPool) -> str:
    with pool.connection() as conn:
        conn.execute("select id from tf_teams order by id for update")
        state = _load_state(conn)
        if state.proposal is None:
            return "막힘: 확정할 배정안이 없음"
        if not state.closed:
            return "막힘: 모집이 마감되지 않음"
        errors = validate_plan(state.teams, state.unassigned, state.proposal.plan)
        if errors:
            return f"막힘: 배정안이 지금 상태와 맞지 않음 ({errors[0]})"
        team_ids = dict(conn.execute("select team_no, id from tf_teams").fetchall())
        by_no = {s.student_no: s for s in state.unassigned}
        for student_no, team_no in state.proposal.plan:
            _insert_member(conn, team_ids[team_no], by_no[student_no].id)
        conn.execute("delete from tf_settings where key = 'proposal'")
    return "승인: 배정을 확정함"


# ---------- 기록 ----------


def log_attempt(pool: ConnectionPool, r: AttemptResult) -> None:
    with pool.connection() as conn:
        conn.execute(
            "insert into tf_ai_logs (attempt, model, outcome, detail, elapsed_ms) values (%s, %s, %s, %s, %s)",
            (r.attempt, r.model, r.outcome, r.detail[:2000], int(r.elapsed_s * 1000)),
        )


def touch_keepalive(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute("select count(*) from tf_students")
        _set(conn, "last_keepalive", conn.execute("select now()::text").fetchone()[0])
