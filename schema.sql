-- 2026-10-16 22:09 KST
-- 팀 편성 앱의 테이블. 6장 실습 테이블과 같은 DB에 있으므로 모두 tf_ 로 시작한다.
-- 앱은 DATABASE_URL(postgres 사용자)로 직접 접속한다. Supabase의 공개 API(anon 키)로는
-- 읽거나 쓰지 못하도록 모든 테이블에 RLS를 켜고 정책은 만들지 않는다.

create table if not exists tf_students (
    id bigint generated always as identity primary key,
    student_no text not null unique,
    name text not null,
    main_role text check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text not null,          -- bcrypt 해시. 비밀번호를 적힌 그대로 저장하지 않는다
    is_admin boolean not null default false
);

create table if not exists tf_student_sub_roles (
    student_id bigint not null references tf_students (id) on delete cascade,
    role text not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    primary key (student_id, role)
);

create table if not exists tf_teams (
    id bigint generated always as identity primary key,
    team_no int not null unique,
    name text not null unique
);

-- 마지막 자리에 두 명이 동시에 들어가도 (team_id, slot_no) 기본 키 때문에 먼저 도착한 학생만 기록된다.
-- student_id 유일성 제약은 한 학생이 한 팀에만 속하게 한다.
create table if not exists tf_members (
    team_id bigint not null references tf_teams (id) on delete cascade,
    slot_no int not null check (slot_no between 1 and 4),
    student_id bigint not null unique references tf_students (id) on delete cascade,
    primary key (team_id, slot_no)
);

create table if not exists tf_applications (
    id bigint generated always as identity primary key,
    team_id bigint not null references tf_teams (id) on delete cascade,
    student_id bigint not null references tf_students (id) on delete cascade,
    status text not null check (status in ('대기', '승인', '거절')),
    reason text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

-- 한 학생이 결과를 기다리는 지원은 하나뿐이다.
create unique index if not exists tf_applications_one_pending
    on tf_applications (student_id) where status = '대기';

create table if not exists tf_votes (
    application_id bigint not null references tf_applications (id) on delete cascade,
    voter_id bigint not null references tf_students (id) on delete cascade,
    vote text not null check (vote in ('찬성', '거부')),
    created_at timestamptz not null default now(),
    primary key (application_id, voter_id)
);

-- 마감 여부(closed), 확정 전 배정안(proposal), 마지막 예약 질의 시각(last_keepalive)
create table if not exists tf_settings (
    key text primary key,
    value text not null
);

create table if not exists tf_ai_logs (
    id bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    attempt int not null,
    model text not null,
    outcome text not null,
    detail text,
    elapsed_ms int not null
);

alter table tf_students enable row level security;
alter table tf_student_sub_roles enable row level security;
alter table tf_teams enable row level security;
alter table tf_members enable row level security;
alter table tf_applications enable row level security;
alter table tf_votes enable row level security;
alter table tf_settings enable row level security;
alter table tf_ai_logs enable row level security;
