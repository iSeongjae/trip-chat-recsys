"""로그인: 게스트(쿠키만) 또는 Google(openid 범위만 — 이메일·이름·사진은 받지 않음, 계정 고유번호 sub 만 저장)."""
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature
from . import config, db, security

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


def _login(resp: Response, uid: str, ver: int = 0):
    """쿠키 = 서명한 [uid, session_ver]. 로그아웃하면 DB 의 session_ver 가 올라가 그 전에 발급한 쿠키는 모두 무효."""
    resp.set_cookie(COOKIE, _ser.dumps([uid, ver]), max_age=365 * 86400, httponly=True, samesite='lax',
                    secure=config.BASE_URL.startswith('https'))


def _read(request: Request):
    """쿠키 → (uid, session_ver). 예전 쿠키(uid 문자열만)는 session_ver 0. 잘못된 값이면 None."""
    try:
        v = _ser.loads(request.cookies.get(COOKIE, ''))
        uid, ver = (v, 0) if isinstance(v, str) else (str(v[0]), int(v[1]))
        return uid, ver
    except (BadSignature, TypeError, ValueError, IndexError, KeyError):
        return None


def current_user(request: Request) -> str:
    r = _read(request)
    if not r:
        raise HTTPException(401, '로그인 필요')
    uid, ver = r
    try:
        ok = db.touch(uid, ver)     # 마지막 이용 시각 갱신 (게스트 30일 만료 기준). 로그아웃한 쿠키면 False
    except Exception:               # 예전 SQLite 쿠키('g_…') 등 uuid 가 아닌 값
        ok = False
    if not ok:
        raise HTTPException(401, '로그인 필요')
    return uid


@router.get('/api/auth/config')
def auth_config():
    return {'google': _oauth is not None}


@router.post('/api/auth/guest', dependencies=[Depends(security.GUEST)])
def guest(response: Response):
    uid = db.new_user()
    _login(response, uid)
    return {'user_id': uid, 'guest': True}


@router.get('/auth/google/login', dependencies=[Depends(security.BURST)])
async def google_login(request: Request):
    if not _oauth:
        raise HTTPException(501, 'Google 로그인 설정 안 됨 (GOOGLE_CLIENT_ID/SECRET)')
    return await _oauth.google.authorize_redirect(request, config.BASE_URL + '/auth/google/callback')


@router.get('/auth/google/callback')
async def google_callback(request: Request):
    if not _oauth:
        raise HTTPException(501, 'Google 로그인 설정 안 됨')
    try:
        tok = await _oauth.google.authorize_access_token(request)   # state·nonce 검증은 authlib 이 함
        sub = tok['userinfo']['sub']
    except Exception:                                                # 로그인 취소(access_denied)·state 불일치·만료
        return RedirectResponse('/#/start')
    r = db.one('select id, session_ver from users where google_sub = %s', sub)
    uid, ver = (str(r['id']), r['session_ver']) if r else (db.new_user(google_sub=sub), 0)
    resp = RedirectResponse('/#/chat')
    _login(resp, uid, ver)
    return resp


@router.post('/api/auth/logout')
def logout(request: Request, response: Response):
    r = _read(request)
    if r:
        try:
            db.run('update users set session_ver = session_ver + 1 where id = %s', r[0])   # 이 계정의 기존 쿠키 전부 무효
        except Exception:
            pass
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
