"""이제 뭐 하지? 프로토타입 서버.
실행: (server/ 에서) uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import config, db, service
from .auth import router as auth_router
from .routers import chat, places, me

STATIC = os.path.join(os.path.dirname(__file__), '..', 'static')


async def _purge_daily():
    """게스트 30일 만료 처리 (DB 함수 purge_expired). 실패해도 서버는 계속."""
    while True:
        try:
            await asyncio.to_thread(db.purge_guests)
        except Exception as ex:
            print('purge 실패:', ex)
        await asyncio.sleep(86400)


@asynccontextmanager
async def lifespan(app):
    # 동기 엔드포인트는 스레드풀에서 돈다. /api/chat 이 LLM 응답(1.5~2.5초)을 기다리며 스레드를 잡고 있어도
    # 다른 요청이 줄 서지 않게 기본 40 → 200 (대부분 네트워크 대기라 CPU 부담은 작음)
    import anyio
    anyio.to_thread.current_default_thread_limiter().total_tokens = 200
    db.init()
    service.items()      # 아이템 37만 곳 메모리 로드 (약 1초)
    service.stations(); service.name_index(); service.cg.grid(service.items())   # 인덱스 미리 만들기
    task = asyncio.create_task(_purge_daily()) if config.PURGE_IN_APP else None   # 기본은 DB(pg_cron)가 처리
    yield
    if task: task.cancel()
    db.close()


app = FastAPI(title='이제 뭐 하지?', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, https_only=config.BASE_URL.startswith('https'))  # Google OAuth state 용
for r in (auth_router, chat.router, places.router, me.router):
    app.include_router(r)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/health')
def health():
    return {'ok': True, 'items': len(service.items()), 'llm': bool(config.OPENAI_API_KEY)}


@app.get('/robots.txt', include_in_schema=False)
def robots():
    return FileResponse(os.path.join(STATIC, 'robots.txt'), media_type='text/plain')


@app.get('/')
def index():
    return FileResponse(os.path.join(STATIC, 'index.html'))
