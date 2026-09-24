"""Supabase(Postgres) 접속 공용 모듈. 접속 정보는 프로젝트 루트 .env 의 SUPABASE_DB_{HOST,PORT,NAME,USER,PASSWORD} (gitignore).
연결 실패는 지수 백오프로 재시도한다 (프로젝트 일시정지·네트워크 순단 대비)."""
import os, time, random, logging
import psycopg

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
log = logging.getLogger('pg')
RETRYABLE = (psycopg.OperationalError, psycopg.InterfaceError)


def load_env(path=os.path.join(ROOT, '.env')):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def conninfo():
    load_env()
    missing = [k for k in ('HOST', 'PORT', 'NAME', 'USER', 'PASSWORD') if not os.environ.get(f'SUPABASE_DB_{k}')]
    if missing:
        raise SystemExit(f".env 에 SUPABASE_DB_{', SUPABASE_DB_'.join(missing)} 가 없음")
    e = lambda k: os.environ[f'SUPABASE_DB_{k}']
    return dict(host=e('HOST'), port=e('PORT'), dbname=e('NAME'), user=e('USER'), password=e('PASSWORD'),
                sslmode='require', connect_timeout=15, application_name='wsid-tools')


def fatal(ex):
    """다시 시도해도 소용없는 오류 (비밀번호·권한·DB 이름 틀림)."""
    m = str(ex).lower()
    return any(k in m for k in ('password authentication failed', 'no pg_hba.conf', 'does not exist', 'permission denied'))


def backoff(attempt, base=2.0, cap=60.0):
    return min(cap, base * 2 ** attempt) * (0.5 + random.random() / 2)   # 지터


def connect(attempts=5, **kw):
    """재시도하며 연결. 끝내 실패하면 마지막 예외를 그대로 올린다."""
    for i in range(attempts):
        try:
            return psycopg.connect(**conninfo(), **kw)
        except RETRYABLE as ex:
            if i == attempts - 1 or fatal(ex):
                raise
            wait = backoff(i)
            log.warning('연결 실패 (%s/%s): %s → %.0f초 뒤 재시도', i + 1, attempts, str(ex).splitlines()[0][:120], wait)
            time.sleep(wait)
