"""설정: 프로젝트 루트 .env 를 읽는다 (gitignore). 서버 전용 값:
SESSION_SECRET(쿠키 서명, 없으면 실행마다 새로 만들어 로그인이 풀림), GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET(없으면 게스트만),
BASE_URL(구글 콜백 주소 기준), OPENAI_MODEL(기본 gpt-5-mini), DAILY_CHAT_LIMIT(기본 100), ITEMS_PATH, DB_PATH.
PROXY_SECRET(배포: web nginx 만 api 를 부를 수 있게), LLM_DAILY_LIMIT·GUEST_PER_IP_DAILY·RATE_PER_MIN(남용·비용 제한)."""
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
LLM_DAILY_LIMIT = int(os.environ.get('LLM_DAILY_LIMIT', 2000))      # 서비스 전체 하루 LLM 호출 상한. 넘으면 규칙 파서로 (비용 가드)
GUEST_PER_IP_DAILY = int(os.environ.get('GUEST_PER_IP_DAILY', 30))  # IP 하나가 하루에 만들 수 있는 게스트 수 (사용자별 한도 우회 방지)
RATE_PER_MIN = int(os.environ.get('RATE_PER_MIN', 30))              # IP 별 1분 요청 수 (대화·칩·로그인)
PROXY_SECRET = os.environ.get('PROXY_SECRET')                       # 있으면 이 값을 X-Proxy-Secret 으로 붙인 요청만 받음 (security.py)
DB_POOL_MAX = int(os.environ.get('DB_POOL_MAX', 8))   # Supabase 무료(NANO) 최대 연결 60 중
GEOIP_PATH = os.environ.get('GEOIP_PATH', os.path.join(ROOT, 'data', 'geoip', 'dbip-country-lite.mmdb'))   # IP → 국가 (DB-IP Lite, CC BY 4.0)
PURGE_IN_APP = os.environ.get('PURGE_IN_APP') == '1'   # 게스트 만료 정리는 Supabase pg_cron 이 매일 실행. 서버에서도 돌리려면 1
APP_ENV = os.environ.get('APP_ENV', 'dev')           # turn_logs.versions.env 로 남김 (dev 로그는 분석에서 뺄 수 있게)
LOCATION_DECIMALS = 2              # 저장하는 GPS 좌표 자릿수 (약 1km, 방침: 동네 단위만 저장)
