"""설정: 프로젝트 루트 .env 를 읽는다 (gitignore). 서버 전용 값:
SESSION_SECRET(쿠키 서명, 없으면 실행마다 새로 만들어 로그인이 풀림), GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET(없으면 게스트만),
BASE_URL(구글 콜백 주소 기준), OPENAI_MODEL(기본 gpt-5-mini), DAILY_CHAT_LIMIT(기본 100), ITEMS_PATH, DB_PATH."""
import os, secrets

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_env = os.path.join(ROOT, '.env')
if os.path.exists(_env):
    for line in open(_env):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SESSION_SECRET = os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5-mini')  # nano 는 종류를 일본어로 뽑거나 놓침 (2026-09-24 비교)
LLM_MOCK = os.environ.get('LLM_MOCK') == '1'   # 부하 테스트용: LLM 대신 규칙 파서 + 1.5~2.5초 지연 (비용 없음)
DAILY_CHAT_LIMIT = int(os.environ.get('DAILY_CHAT_LIMIT', 100))
DB_POOL_MAX = int(os.environ.get('DB_POOL_MAX', 8))   # Supabase 무료(NANO) 최대 연결 60 중
GEOIP_PATH = os.environ.get('GEOIP_PATH', os.path.join(ROOT, 'data', 'geoip', 'dbip-country-lite.mmdb'))   # IP → 국가 (DB-IP Lite, CC BY 4.0)
PURGE_IN_APP = os.environ.get('PURGE_IN_APP') == '1'   # 게스트 만료 정리는 Supabase pg_cron 이 매일 실행. 서버에서도 돌리려면 1
APP_ENV = os.environ.get('APP_ENV', 'dev')           # turn_logs.versions.env 로 남김 (dev 로그는 분석에서 뺄 수 있게)
LOCATION_DECIMALS = 2              # 저장하는 GPS 좌표 자릿수 (약 1km, 방침: 동네 단위만 저장)
