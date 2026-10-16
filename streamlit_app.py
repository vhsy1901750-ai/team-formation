# 2026-10-16 22:21 KST
"""팀 편성 웹 앱 화면. 화면 요소의 key는 공고 2.7절 표와 같아야 한다."""
import streamlit as st

from tf import ai, db
from tf.config import get_secret, load_local_env
from tf.models import Proposal, Student, User
from tf.roster import RosterError, parse_roster
from tf.solver import explain_infeasible, find_assignment

REFRESH_SECONDS = 3
DB_ERROR = "막힘: DB 처리 중 오류가 생김. 잠시 뒤 다시 시도해 주세요."

st.set_page_config(page_title="팀 편성", page_icon="👥")
load_local_env()


@st.cache_resource
def get_pool():
    pool = db.make_pool(get_secret("DATABASE_URL"))
    db.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    return pool


# ---------- 공통 ----------


def show_result() -> None:
    with st.container(key="result"):
        text = st.session_state.get("result")
        if text:
            st.write(text)


def act(fn, *args) -> None:
    """단추 처리. 결과 문장을 세션에 저장해 두고 화면을 다시 그릴 때마다 보여 준다."""
    try:
        st.session_state.result = fn(*args)
    except Exception:
        st.session_state.result = DB_ERROR


def admin_act(fn, *args) -> None:
    user = st.session_state.get("user")
    if user is None or not user.is_admin:
        st.session_state.result = "막힘: 관리자만 할 수 있음"
        return
    act(fn, *args)


def describe(s: Student) -> str:
    subs = ", ".join(s.sub_roles) if s.sub_roles else "없음"
    return f"{s.name}: 주 역할 {s.main_role}, 보조 역할 {subs}"


def team_box(team_no: int, members: list[Student], mine: bool = False):
    box = st.container(key=f"team_{team_no}", border=True)
    with box:
        label = f"**팀{team_no}** ({len(members)}/4명)"
        st.markdown(label + (" :blue-badge[내 팀]" if mine else ""))
        for m in members:
            st.write(describe(m))
        if not members:
            st.caption("팀원 없음")
    return box


# ---------- 로그인 ----------


def login_view(pool) -> None:
    st.title("팀 편성")
    student_no = st.text_input("학번", key="login_student_no")
    password = st.text_input("비밀번호", type="password", key="login_password")
    if st.button("로그인", key="login_submit"):
        try:
            user = db.authenticate(pool, student_no, password)
        except Exception:
            user = None
            st.session_state.result = DB_ERROR
        else:
            if user is None:
                st.session_state.result = "막힘: 학번이나 비밀번호가 틀림"
        if user is not None:
            st.session_state.user = user
            st.session_state.result = ""
            st.rerun()
    show_result()


def logout() -> None:
    for key in ["user", "result", "assign_status", "login_password"]:
        st.session_state.pop(key, None)


# ---------- 학생 화면 ----------


def student_view(pool, user: User, state) -> None:
    my_team = next((t for t, ms in state.teams.items() if any(m.id == user.id for m in ms)), None)
    my_pending = next((a for a in state.pending if a.applicant.id == user.id), None)

    if my_team is not None:
        st.write(f"내 팀: 팀{my_team}")
    elif my_pending is not None:
        st.write(f"팀{my_pending.team_no}에 지원하고 결과를 기다리는 중")
    else:
        st.write("아직 팀이 없음")
    if state.closed:
        st.info("모집이 마감됨")

    can_apply = my_team is None and my_pending is None and not state.closed
    for t in sorted(state.teams):
        with team_box(t, state.teams[t], mine=(t == my_team)):
            st.button("이 팀에 지원", key=f"apply_{t}", disabled=not can_apply, on_click=act, args=(db.apply, pool, user.id, t))

    if my_team is None:
        return
    apps = [a for a in state.pending if a.team_no == my_team]
    st.subheader("내 팀에 들어온 지원")
    if not apps:
        st.caption("기다리는 지원 없음")
    members = state.teams[my_team]
    for a in apps:
        no = a.applicant.student_no
        my_vote = a.votes.get(user.id)
        with st.container(border=True):
            st.write(describe(a.applicant))
            yes, no_ = st.columns(2)
            yes.button("찬성", key=f"vote_yes_{no}", disabled=my_vote is not None, on_click=act, args=(db.vote, pool, user.id, no, True))
            no_.button("거부", key=f"vote_no_{no}", disabled=my_vote is not None, on_click=act, args=(db.vote, pool, user.id, no, False))
            waiting = sum(1 for m in members if m.id not in a.votes)
            st.caption(f"내 투표: {my_vote}" if my_vote else f"아직 투표하지 않은 팀원 {waiting}명")


# ---------- 관리자 화면 ----------


def start_roster(pool) -> str:
    uploaded = st.session_state.get("admin_roster_file")
    if uploaded is None:
        return "막힘: 명단 CSV 파일이 없음"
    try:
        rows = parse_roster(uploaded.getvalue())
    except RosterError as e:
        return f"막힘: 명단 CSV 오류 ({e})"
    st.session_state.pop("assign_status", None)
    return db.reset_with_roster(pool, rows, int(st.session_state.admin_team_count))


def confirm(pool) -> str:
    text = db.confirm_proposal(pool)
    if text.startswith("승인"):
        st.session_state.pop("assign_status", None)
    return text


def run_assignment(pool) -> list[str]:
    """AI 배정을 하고 assign_status에 남길 줄을 돌려준다. 첫 줄은 result에도 쓴다."""
    state = db.load_state(pool)
    if not state.closed:
        return ["막힘: 모집이 마감되지 않음"]
    if not state.unassigned:
        return ["막힘: 팀이 없는 학생이 없음"]

    # 규칙을 지키는 배정이 아예 없으면 AI를 부르지 않는다. 있으면 3차까지 실패했을 때 이것을 쓴다.
    fallback = find_assignment(state.teams, state.unassigned)
    if fallback is None:
        return [f"막힘: 규칙을 지키는 배정이 없음 ({explain_infeasible(state.teams, state.unassigned)})"]

    waiting = st.empty()

    def on_wait(attempt: int, model: str, elapsed: float) -> None:
        waiting.info(f"{attempt}차 모델({model})의 응답을 기다리는 중 ({elapsed:.0f}초)")

    plan, attempts = ai.run_ai_assignment(
        state.teams, state.unassigned, api_key=get_secret("OPENROUTER_API_KEY") or "", on_wait=on_wait
    )
    waiting.empty()
    for a in attempts:
        try:
            db.log_attempt(pool, a)
        except Exception:
            pass
    notes = [f"{a.attempt}차 모델 {a.model}: {a.outcome} ({a.elapsed_s:.0f}초) {a.detail}".rstrip() for a in attempts]
    if plan is not None:
        source = f"{attempts[-1].attempt}차 모델 {attempts[-1].model}"
    else:
        plan, source = fallback, "3차 모델까지 실패해서 앱이 직접 배정"
    db.save_proposal(pool, Proposal(plan=plan, source=source, notes=notes))
    return [f"승인: 배정안을 만듦 ({source})", *notes]


def admin_view(pool, state) -> None:
    st.subheader("명단 올리기")
    st.file_uploader("명단 CSV", type=["csv"], key="admin_roster_file")
    st.number_input("팀 수", min_value=1, max_value=10, value=3, step=1, key="admin_team_count")
    st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=admin_act, args=(start_roster, pool))

    st.subheader("모집 마감")
    if state.closed:
        st.info("모집이 마감됨")
    st.button("모집 마감", key="admin_close", on_click=admin_act, args=(db.close_recruiting, pool))
    with st.container(key="unassigned", border=True):
        st.markdown("**팀이 없는 학생**")
        st.write(", ".join(s.name for s in state.unassigned) or "없음")

    st.subheader("배정")
    clicked = st.button("AI 배정", key="admin_assign")
    with st.container(key="assign_status", border=True):
        if clicked:
            user = st.session_state.get("user")
            if user is None or not user.is_admin:
                lines = ["막힘: 관리자만 할 수 있음"]
            else:
                try:
                    lines = run_assignment(pool)
                except Exception:
                    lines = [DB_ERROR]
            st.session_state.assign_status = lines
            st.session_state.result = lines[0]
            st.rerun()
        lines = st.session_state.get("assign_status") or ["아직 배정하지 않음"]
        for line in lines:
            st.write(line)
        if state.proposal:
            by_no = {s.student_no: s for s in state.unassigned}
            st.markdown(f"**배정안** ({state.proposal.source})")
            st.table(
                [
                    {
                        "이름": by_no[no].name if no in by_no else no,
                        "주 역할": by_no[no].main_role if no in by_no else "",
                        "보조 역할": ", ".join(by_no[no].sub_roles) if no in by_no else "",
                        "배정된 팀": f"팀{t}",
                    }
                    for no, t in state.proposal.plan
                ]
            )
    st.button("배정안 확정", key="admin_confirm", on_click=admin_act, args=(confirm, pool))

    st.subheader("팀 목록")
    for t in sorted(state.teams):
        team_box(t, state.teams[t])


# ---------- 시작 ----------


@st.fragment(run_every=REFRESH_SECONDS)
def body(pool, user: User) -> None:
    """다른 사람의 변경을 3초마다 다시 그린다."""
    show_result()
    try:
        state = db.load_state(pool)
    except Exception:
        st.warning("DB에 잠시 접속하지 못함. 곧 다시 시도함.")
        return
    if user.is_admin:
        admin_view(pool, state)
    else:
        student_view(pool, user, state)


def main() -> None:
    missing = [n for n in ["DATABASE_URL", "ADMIN_PASSWORD", "OPENROUTER_API_KEY"] if not get_secret(n)]
    if missing:
        st.error("설정 값이 없음: " + ", ".join(missing))
        st.stop()
    pool = get_pool()

    user = st.session_state.get("user")
    if user is None:
        login_view(pool)
        return

    with st.container(key="whoami"):
        st.write(f"로그인: {user.name} ({user.student_no})")
    st.button("로그아웃", key="logout", on_click=logout)
    body(pool, user)


main()
