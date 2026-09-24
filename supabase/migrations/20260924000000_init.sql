-- 이제 뭐 하지? — Supabase(Postgres) 초기 스키마 (2026-09-24)
-- 설계 문서: docs/db_schema.md    적용: python3 scripts/db/migrate.py
--
-- 원칙
--  * 서버(FastAPI)만 DB 에 직접 연결한다. Data API(PostgREST)는 꺼 두고, 모든 테이블에 RLS 를 켜고 정책을 두지 않는다.
--  * 사용자 GPS 정확 좌표는 저장하지 않는다: geohash 6자리(약 1km)만. 직접 등록 스팟은 사용자 콘텐츠라 예외.
--  * 이메일·이름·사진은 받지 않는다 (Google 은 sub 만). Supabase Auth 는 쓰지 않는다.
--  * 두 종류로 나눈다.
--      개인 데이터 (users, profiles, trip_state, messages, spots, visits, saved, user_feedback, usage_daily)
--          → 탈퇴·게스트 만료 때 삭제.
--      행동 로그 (trips, turn_logs, reaction_logs)
--          → 지우지 않고 계속 적재. 사람 대신 actor(무작위 uuid)로만 묶는다. users 가 지워지면 actor 와 사람의 연결이 끊겨
--            익명 로그가 된다. 이때 발화 원문(query)은 지우고 위치는 geohash 4자리(약 20km)로 거칠게 한다 (forget_user).
--  * 행동 로그는 대화(추천) 한 번 = turn_logs 한 줄, 사용자 반응 한 번 = reaction_logs 한 줄.

create extension if not exists pgcrypto;

-- ═══════════════════════ 개인 데이터 ═══════════════════════
create table users (
  id            uuid primary key default gen_random_uuid(),
  google_sub    text unique,                                  -- null 이면 게스트
  actor         uuid not null unique default gen_random_uuid(),  -- 행동 로그용 가명 id
  created_at    timestamptz not null default now(),
  last_seen_at  timestamptz not null default now()
);

create table profiles (                                     -- japan_rec.profile 의 stable / taste
  user_id      uuid primary key references users(id) on delete cascade,
  stable       jsonb not null default '{}',
  taste        jsonb not null default '{}',
  n_reactions  int   not null default 0,
  updated_at   timestamptz not null default now()
);

create table trips (                                        -- 여행 = 행동 로그 묶음. 사용자를 지워도 남김
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references users(id) on delete set null,
  actor        uuid not null,
  started_at   timestamptz not null default now(),
  ended_at     timestamptz,
  start_label  text,                                          -- '간사이 국제공항' 등 (삭제 시 null)
  start_method text check (start_method in ('gps', 'airport', 'search', 'place'))
);
create index on trips (actor);
create unique index trips_one_open on trips (user_id) where ended_at is null;

create table trip_state (                                   -- 세션 상태 (현재 위치·방문 목록). 자주 덮어씀
  trip_id       uuid primary key references trips(id) on delete cascade,
  current_label text,
  current_geo   text,                                         -- geohash6
  current_place text,                                         -- 마지막으로 고른 장소 id (정확 위치 대신)
  visited       text[] not null default '{}',
  intent        jsonb  not null default '{}',
  last_shown    text[] not null default '{}',
  last_turn     uuid,
  turn          int    not null default 0,
  updated_at    timestamptz not null default now()
);

create table messages (                                     -- 채팅 화면 복원용 (발화 원문 포함 → 개인 데이터)
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  trip_id     uuid references trips(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  text        text,
  turn_id     uuid,                                           -- turn_logs.id
  payload     jsonb,
  created_at  timestamptz not null default now()
);
create index on messages (trip_id, created_at);

create table spots (                                        -- 직접 등록(발자국)
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  name        text not null check (length(name) <= 100),
  lat         double precision not null,
  lon         double precision not null,
  memo        text check (length(memo) <= 500),
  created_at  timestamptz not null default now()
);

create table visits (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  trip_id     uuid references trips(id) on delete set null,
  place_id    text,
  spot_id     uuid references spots(id) on delete cascade,
  source      text not null check (source in ('recommendation', 'mentioned', 'manual')),
  turn_id     uuid,
  rating      numeric(2,1) check (rating between 0 and 5),
  memo        text check (length(memo) <= 500),
  visited_at  timestamptz not null default now(),
  check ((place_id is null) <> (spot_id is null))
);
create index on visits (user_id, visited_at desc);

create table saved (
  user_id     uuid not null references users(id) on delete cascade,
  place_id    text not null,
  turn_id     uuid,
  saved_at    timestamptz not null default now(),
  primary key (user_id, place_id)
);

create table user_feedback (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references users(id) on delete cascade,
  turn_id     uuid,
  kind        text not null check (kind in ('good', 'bad', 'wrong_info', 'bug', 'idea')),
  text        text check (length(text) <= 2000),
  created_at  timestamptz not null default now()
);

create table usage_daily (
  user_id  uuid not null references users(id) on delete cascade,
  day      date not null,
  chats    int  not null default 0,
  primary key (user_id, day)
);

-- ═══════════════════════ 행동 로그 ═══════════════════════
create table turn_logs (                                    -- 대화(추천) 한 번 = 한 줄
  id          uuid primary key default gen_random_uuid(),
  actor       uuid not null,
  trip_id     uuid references trips(id) on delete set null,
  turn_no     int,
  source      text not null check (source in ('chat', 'chip')),
  query       text,                 -- 사용자 발화 원문 (칩이면 칩 이름). forget_user 때 null
  intent      jsonb not null,       -- 파서가 뽑고 프로필로 채운 최종 조건 {next_category, include_sub, theme, max_distance_km, …}
  context     jsonb not null,       -- {area_geo, location_method, radius_km_asked, radius_km_used, n_candidates, trace, notes, personalization_w}
  candidates  jsonb not null,       -- 보여준 목록 [{rank, place_id, slot, score, pop, taste, dist_m, flags}]
  answer      text,                 -- LLM 답변 (+ 요약 문장)
  llm         jsonb,                -- {model, prompt_version, input_tokens, cached_tokens, output_tokens, latency_ms, status}
  versions    jsonb not null,       -- {ranker, items, variant}
  latency_ms  int,                  -- 요청 전체 처리 시간
  created_at  timestamptz not null default now()
);
create index on turn_logs (created_at, id);
create index on turn_logs (actor, created_at);

create table reaction_logs (                                -- 사용자 반응 한 번 = 한 줄
  id          bigint generated always as identity primary key,
  turn_id     uuid references turn_logs(id) on delete set null,   -- 어느 추천에서 나온 반응인지 (추천 밖 반응이면 null)
  actor       uuid not null,
  trip_id     uuid references trips(id) on delete set null,
  place_id    text,
  rank        smallint,                                        -- 몇 위였는지
  type        text not null check (type in (
                'card_open', 'map_open', 'pin_click', 'select', 'directions_open',
                'save', 'unsave', 'skip', 'share', 'wiki_open', 'rate', 'mark_visited')),
  props       jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index on reaction_logs (created_at, id);
create index on reaction_logs (turn_id);

-- 학습용: 보여준 후보 1개 = 1행, 반응 여부 라벨
create view v_candidate_outcomes as
select t.id as turn_id, t.actor, t.trip_id, t.source, t.created_at, t.intent, t.versions,
       (c->>'rank')::int as rank, c->>'place_id' as place_id, c->>'slot' as slot,
       (c->>'score')::real as score, (c->>'pop')::real as pop, (c->>'taste')::real as taste, (c->>'dist_m')::int as dist_m,
       coalesce(bool_or(r.type = 'select'), false)    as selected,
       coalesce(bool_or(r.type = 'save'), false)      as saved,
       coalesce(bool_or(r.type = 'skip'), false)      as skipped,
       coalesce(bool_or(r.type = 'card_open'), false) as opened
from turn_logs t
cross join lateral jsonb_array_elements(t.candidates) c
left join reaction_logs r on r.turn_id = t.id and r.place_id = c->>'place_id'
group by t.id, c;

-- ═══════════════════════ 삭제 (개인정보 처리방침) ═══════════════════════
create or replace function forget_user(uid uuid) returns void language plpgsql as $$
declare a uuid;
begin
  select actor into a from users where id = uid;
  if a is null then return; end if;
  update turn_logs set query = null,
         context = jsonb_set(context, '{area_geo}', to_jsonb(left(context->>'area_geo', 4)), false)
   where actor = a;                                                        -- 발화 원문 삭제, 위치 1km → 20km
  update trips set start_label = null where actor = a;
  delete from trip_state where trip_id in (select id from trips where actor = a);
  delete from users where id = uid;          -- profiles·messages·spots·visits·saved·user_feedback·usage_daily 는 cascade
end $$;

create or replace function purge_expired() returns void language plpgsql as $$
declare u uuid;
begin
  for u in select id from users where google_sub is null and last_seen_at < now() - interval '30 days' loop   -- 게스트 30일
    perform forget_user(u);
  end loop;
end $$;
-- 매일 실행: create extension if not exists pg_cron;  select cron.schedule('purge-expired', '0 4 * * *', 'select purge_expired()');

-- ═══════════════════════ RLS: 서버 전용 ═══════════════════════
do $$
declare t text;
begin
  foreach t in array array['users','profiles','trips','trip_state','messages','spots','visits','saved','user_feedback',
                           'usage_daily','turn_logs','reaction_logs']
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
revoke all on v_candidate_outcomes from anon, authenticated;
