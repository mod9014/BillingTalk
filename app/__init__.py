"""
FastAPI 앱 팩토리.

책임:
  - 모든 라우트(설정/업로드/예약등록/상태조회) 등록
  - frontend/ 정적 파일 서빙
  - config가 미완성이면 "/" 접속 시 setup.html로, 완성되면 index.html로 리다이렉트

주의: CORS 등 미들웨어는 로컬 전용이라 불필요 — 넣지 않는다.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import is_configured
from app.routes import schedule, service, setup, status, upload

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app(config: dict) -> FastAPI:
    app = FastAPI(title="오피스텔 청구 알림톡")
    app.state.config = config

    app.include_router(setup.router)
    app.include_router(upload.router)
    app.include_router(schedule.router)
    app.include_router(status.router)
    app.include_router(service.router)

    @app.get("/")
    async def root():
        target = "/index.html" if is_configured(app.state.config) else "/setup.html"
        return RedirectResponse(url=target)

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app
