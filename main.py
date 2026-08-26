"""
실행 진입점. PyInstaller --onefile 빌드 대상.

책임:
  1. 로컬 config.json 존재 확인 (없으면 최초 실행으로 간주)
  2. FastAPI 앱 생성 (app.create_app)
  3. 기본 브라우저로 대시보드 자동 오픈
  4. uvicorn을 127.0.0.1에만 바인딩 (외부 노출 금지 — host를 절대 0.0.0.0으로 바꾸지 말 것)

TODO: 포트 충돌 시 대체 포트 탐색 로직
"""

import webbrowser
import threading
import uvicorn

from app import create_app
from app.config import ensure_config

HOST = "127.0.0.1"
PORT = 8000


def open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    config = ensure_config()
    app = create_app(config)

    threading.Timer(1.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
