"""로그인: 게스트(쿠키만) 또는 Google(openid 범위만 — 이메일·이름·사진은 받지 않음, 계정 고유번호 sub 만 저장)."""
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature
from . import config, db

COOKIE = 'uid'
_ser = URLSafeSerializer(config.SESSION_SECRET, salt='uid')
router = APIRouter()

_oauth = None
if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
    from authlib.integrations.starlette_client import OAuth
    _oauth = OAuth()
    _oauth.register('google', client_id=config.GOOGLE_CLIENT_ID, client_secret=config.GOOGLE_CLIENT_SECRET,
                    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                    client_kwargs={'scope': 'openid'})


def _login(resp: Response, uid: str):
    resp.set_cookie(COOKIE, _ser.dumps(uid), max_age=365 * 86400, httponly=True, samesite='lax',
                    secure=config.BASE_URL.startswith('https'))


def current_user(request: Request) -> str:
    try:
        uid = _ser.loads(request.cookies.get(COOKIE, ''))
    except BadSignature:
        raise HTTPException(401, '로그인 필요')
    try:
        ok = db.touch(uid)          # 마지막 이용 시각 갱신 (게스트 30일 만료 기준)
    except Exception:               # 예전 SQLite 쿠키('g_…') 등 uuid 가 아닌 값
        ok = False
    if not ok:
        raise HTTPException(401, '로그인 필요')
    return uid


@router.get('/api/auth/config')
def auth_config():
    return {'google': _oauth is not None}


@router.post('/api/auth/guest')
def guest(response: Response):
    uid = db.new_user()
    _login(response, uid)
    return {'user_id': uid, 'guest': True}


@router.get('/auth/google/login')
async def google_login(request: Request):
    if not _oauth:
        raise HTTPException(501, 'Google 로그인 설정 안 됨 (GOOGLE_CLIENT_ID/SECRET)')
    return await _oauth.google.authorize_redirect(request, config.BASE_URL + '/auth/google/callback')


@router.get('/auth/google/callback')
async def google_callback(request: Request):
    tok = await _oauth.google.authorize_access_token(request)
    sub = tok['userinfo']['sub']
    r = db.one('select id from users where google_sub = %s', sub)
    uid = str(r['id']) if r else db.new_user(google_sub=sub)
    resp = RedirectResponse('/#/chat')
    _login(resp, uid)
    return resp


@router.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {'ok': True}


@router.get('/api/me')
def me(uid: str = Depends(current_user)):
    from . import service as sv
    u = db.one('select google_sub is not null as google from users where id = %s', uid)
    return {'user_id': uid, 'google': bool(u['google']), 'current': sv.public_current(db.load_profile(uid, sv.pf.new_profile))}


@router.delete('/api/me')
def withdraw(response: Response, uid: str = Depends(current_user)):
    """탈퇴: 개인 데이터는 바로 삭제, 행동 로그는 익명으로 남김 (개인정보 처리방침 2항)."""
    db.delete_user(uid)
    response.delete_cookie(COOKIE)
    return {'ok': True}
