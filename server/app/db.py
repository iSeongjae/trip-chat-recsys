"""저장소: Supabase(Postgres). 스키마는 supabase/migrations (scripts/db/migrate.py 로 적용).
장소 37만 곳은 DB 가 아니라 메모리(japan_rec.recommender.items).

- 개인 데이터: users, profiles, trip_state(session), messages, spots, visits, saved, user_feedback, usage_daily
- 행동 로그: trips, turn_logs(대화 한 번 = 한 줄), reaction_logs(반응 한 번 = 한 줄) — actor 로만 묶음
연결: .env 의 SUPABASE_DB_{HOST,PORT,NAME,USER,PASSWORD} (Session pooler). 커넥션 풀 사용.
"""
import json, os, logging
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from . import config

log = logging.getLogger('db')
_pool = None


def init():
    global _pool
    if _pool is None:
        e = lambda k: os.environ[f'SUPABASE_DB_{k}']
        missing = [k for k in ('HOST', 'PORT', 'NAME', 'USER', 'PASSWORD') if not os.environ.get(f'SUPABASE_DB_{k}')]
        if missing:
            raise RuntimeError(f".env 에 SUPABASE_DB_{', SUPABASE_DB_'.join(missing)} 가 없음")
        conninfo = f"host={e('HOST')} port={e('PORT')} dbname={e('NAME')} user={e('USER')} password={e('PASSWORD')} sslmode=require connect_timeout=15 application_name=wsid-api"
        # 꺼낼 때마다 연결 확인(check)을 하면 쿼리마다 왕복이 한 번 더 생겨 느려진다(한국→도쿄 42ms → 98ms).
        # 대신 오래 쉰 연결은 버리고(max_idle), 끊긴 연결에서 난 오류는 _retry 가 새 연결로 한 번 더 시도한다.
        _pool = ConnectionPool(conninfo, min_size=2, max_size=config.DB_POOL_MAX, open=True, timeout=20,
                               kwargs={'row_factory': dict_row, 'autocommit': True}, max_idle=120, max_lifetime=1800)
        _pool.wait(timeout=30)
        one('select 1 as ok from turn_logs limit 1')   # 스키마 적용 여부 확인 (없으면 여기서 오류)


def close():
    if _pool: _pool.close()


def _adapt(args):
    """dict 는 jsonb 로. list 는 text[] 로 그대로 (jsonb 배열이 필요하면 호출하는 쪽에서 Jsonb 로 감쌈)."""
    return [Jsonb(a) if isinstance(a, dict) else a for a in args]


def _retry(fn):
    """끊긴 연결(서버 재시작·유휴 종료)이면 한 번만 새 연결로 다시."""
    import psycopg
    try:
        return fn()
    except (psycopg.OperationalError, psycopg.InterfaceError) as ex:
        log.warning('DB 연결 오류, 한 번 재시도: %s', str(ex).splitlines()[0][:120])
        _pool.check()
        return fn()


def rows(sql, *args):
    def f():
        with _pool.connection() as c:
            return c.execute(sql, _adapt(args)).fetchall()
    return _retry(f)


def one(sql, *args):
    r = rows(sql, *args)
    return r[0] if r else None


def run(sql, *args):
    """쓰기. RETURNING 이 있으면 첫 행의 첫 값을 돌려준다."""
    def f():
        with _pool.connection() as c:
            cur = c.execute(sql, _adapt(args))
            if cur.description:
                r = cur.fetchone()
                return next(iter(r.values())) if r else None
    return _retry(f)


# ───────── 사용자 ─────────
def new_user(google_sub=None):
    return str(run('insert into users(google_sub) values (%s) returning id', google_sub))


def actor(uid):
    r = one('select actor from users where id = %s', uid)
    return str(r['actor']) if r else None


def touch(uid, ver=0):
    """마지막 이용 시각 갱신. 없는 사용자이거나 로그아웃으로 무효가 된 쿠키(session_ver 다름)면 False."""
    return run('update users set last_seen_at = now() where id = %s and session_ver = %s returning id', uid, ver) is not None


def delete_user(uid):
    """탈퇴: 개인 데이터 삭제, 행동 로그는 익명으로 남김 (forget_user)."""
    run('select forget_user(%s)', uid)


def purge_guests():
    run('select purge_expired()')


# ───────── 여행·프로필 ─────────
def current_trip(uid, method=None, label=None):
    r = one('select id from trips where user_id = %s and ended_at is null', uid)
    if r:
        return str(r['id'])
    tid = run('insert into trips(user_id, actor, start_method, start_label) select id, actor, %s, %s from users where id = %s '
              'on conflict do nothing returning id', method, label, uid)
    if tid is None:   # 동시에 다른 요청이 만듦
        tid = one('select id from trips where user_id = %s and ended_at is null', uid)['id']
    run('insert into trip_state(trip_id) values (%s) on conflict do nothing', tid)
    return str(tid)


def end_trip(uid):
    run('update trips set ended_at = now() where user_id = %s and ended_at is null', uid)


def load_profile(uid, new):
    """japan_rec.profile 형태의 dict: stable·taste·n_reactions(profiles) + session(현재 여행 trip_state.session)."""
    p = new(uid)
    r = one('select t.id as trip, ts.session, pr.stable, pr.taste, pr.n_reactions from trips t '
            'left join trip_state ts on ts.trip_id = t.id left join profiles pr on pr.user_id = t.user_id '
            'where t.user_id = %s and t.ended_at is null', uid)          # 한 번에 (여행이 없을 때만 따로 만듦)
    if not r:
        current_trip(uid)
        r = one('select t.id as trip, ts.session, pr.stable, pr.taste, pr.n_reactions from trips t '
                'left join trip_state ts on ts.trip_id = t.id left join profiles pr on pr.user_id = t.user_id '
                'where t.user_id = %s and t.ended_at is null', uid)
    if r['stable'] is not None:
        p['stable'], p['taste'], p['n_reactions'] = r['stable'] or p['stable'], r['taste'] or p['taste'], r['n_reactions']
    if r['session']:
        p['session'].update(r['session'])
    p['_trip'] = str(r['trip'])
    return p


def save_profile(p, geo=None):
    """p 는 이미 개인정보 방침대로 가공된 사본(GPS 좌표 반올림)이어야 한다 (service.stored)."""
    uid, tid, s = p['user_id'], p.get('_trip') or current_trip(p['user_id']), p['session']
    run('insert into profiles(user_id, stable, taste, n_reactions, updated_at) values (%s, %s, %s, %s, now()) '
        'on conflict (user_id) do update set stable = excluded.stable, taste = excluded.taste, n_reactions = excluded.n_reactions, updated_at = now()',
        uid, p['stable'], p['taste'], p['n_reactions'])
    cur = s.get('current') or {}
    run('update trip_state set session = %s, current_label = %s, current_geo = %s, current_place = %s, visited = %s, intent = %s, '
        'last_shown = %s, last_turn = %s, turn = %s, updated_at = now() where trip_id = %s',
        s, cur.get('name'), geo, cur.get('place_id'), list(s.get('visited') or []), s.get('intent') or {},
        list(s.get('last_shown') or []), s.get('last_turn'), s.get('turn', 0), tid)


# ───────── 행동 로그 ─────────
def log_turn(uid, trip_id, **f):
    """대화(추천) 한 번 = turn_logs 한 줄. 반환: turn id"""
    return str(run('insert into turn_logs(actor, trip_id, turn_no, source, query, intent, context, candidates, answer, llm, versions, latency_ms) '
                   'select actor, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s from users where id = %s returning id',
                   trip_id, f.get('turn_no'), f['source'], f.get('query'), f.get('intent') or {}, f.get('context') or {},
                   Jsonb(f.get('candidates') or []), f.get('answer'), f.get('llm'), f.get('versions') or {}, f.get('latency_ms'), uid))


def log_reaction(uid, trip_id, type, place_id=None, turn_id=None, rank=None, props=None):
    """반응 한 번 = reaction_logs 한 줄."""
    run('insert into reaction_logs(turn_id, actor, trip_id, place_id, rank, type, props) '
        'select %s, actor, %s, %s, %s, %s, %s from users where id = %s',
        turn_id, trip_id, place_id, rank, type, props or {}, uid)
