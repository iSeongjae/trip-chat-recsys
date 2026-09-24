"""요청 제한·프록시 확인·API 응답 헤더.

- 배포에서는 web(nginx)만 api 를 부른다: nginx 가 X-Proxy-Secret 을 붙이고, api 는 이 값이 맞는 요청만 받는다.
  (api 의 run.app 주소로 바로 들어와 nginx 의 요청 크기 제한을 건너뛰거나 IP 헤더를 속이는 것을 막음)
- 사용자 IP 는 nginx 가 X-Client-IP 로 넘긴 값만 쓴다 (PROXY_SECRET 이 없으면 로컬 개발: 직접 접속한 주소).
- 요청 제한은 IP 별 고정 창 카운터(인스턴스 메모리). Cloud Run 인스턴스가 여러 개면 각자 세므로 최대 인스턴스 수만큼 느슨해짐.
"""
import hmac, threading, time
from collections import defaultdict
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from . import config

MAX_BODY = 64 * 1024     # nginx client_max_body_size 와 같게


def client_ip(request: Request) -> str:
    if config.PROXY_SECRET:
        return request.headers.get('x-client-ip') or ''
    return request.client.host if request.client else ''


class Window:
    """seconds 동안 key 별 limit 번까지."""
    def __init__(self, limit, seconds):
        self.limit, self.seconds, self.w, self.n = limit, seconds, None, defaultdict(int)
        self.lock = threading.Lock()

    def hit(self, key):
        w = int(time.time() // self.seconds)
        with self.lock:
            if w != self.w:
                self.w, self.n = w, defaultdict(int)
            self.n[key] += 1
            return self.n[key] <= self.limit


def per_ip(win: Window, msg: str):
    """FastAPI 의존성: IP 별 요청 제한 (넘으면 429)."""
    def dep(request: Request):
        if not win.hit(client_ip(request)):
            raise HTTPException(429, msg)
    return dep


GUEST = per_ip(Window(config.GUEST_PER_IP_DAILY, 86400), '오늘은 이 네트워크에서 새로 시작할 수 있는 횟수를 다 썼어요')
BURST = per_ip(Window(config.RATE_PER_MIN, 60), '요청이 너무 많아요. 잠시 뒤에 다시 해 주세요')


async def guard(request: Request, call_next):
    """모든 요청: 프록시 확인 → 크기 제한 → (API 응답) 캐시 금지."""
    if config.PROXY_SECRET and not hmac.compare_digest(request.headers.get('x-proxy-secret', ''), config.PROXY_SECRET):
        return JSONResponse({'detail': 'forbidden'}, 403)
    if int(request.headers.get('content-length') or 0) > MAX_BODY:
        return JSONResponse({'detail': '요청이 너무 커요'}, 413)
    resp = await call_next(request)
    if request.url.path.startswith(('/api/', '/auth/')):
        resp.headers['Cache-Control'] = 'no-store'
    return resp
