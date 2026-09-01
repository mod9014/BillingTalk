import os
import socket
import threading
import webbrowser
from pathlib import Path
import sys
import uvicorn
from pystray import Icon, Menu, MenuItem
from PIL import Image

from app import create_app
from app.config import ensure_config

HOST = "127.0.0.1"
PORT_RANGE = range(8000, 8021)   # 8000이 막혀있으면 8001, 8002... 순으로 시도
LOCK_PORT = 47990                # 서비스 포트와 무관한, 중복실행 감지 전용 포트
STATE_DIR = Path(os.getenv("LOCALAPPDATA")) / "local-alimtalk-sender"
PORT_FILE = STATE_DIR / "port.txt"

server = None
_lock_socket = None  


def find_free_port() -> int:
    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, port)) != 0:  # 연결 안 되면 = 비어있음
                return port
    raise RuntimeError("사용 가능한 포트를 찾지 못했습니다 (8000~8010 모두 사용 중)")


def acquire_singleton_lock() -> bool:
    """이미 실행 중이면 False. 최초 실행이면 소켓을 점유한 채 True 반환."""
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind((HOST, LOCK_PORT))
        return True
    except OSError:
        return False


def open_browser(port: int):
    webbrowser.open(f"http://{HOST}:{port}")


def quit_app(icon, item):
    if server:
        server.should_exit = True
    icon.stop()


def run_server(app, port: int):
    global server
    config = uvicorn.Config(app, host=HOST, port=port, log_config=None)
    server = uvicorn.Server(config)
    server.run()
def resource_path(relative_path: str) -> Path:
    """개발 환경과 PyInstaller 빌드 환경 모두에서 리소스 경로를 올바르게 찾는다."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)   # PyInstaller가 리소스를 풀어둔 위치
    else:
        base_path = Path(__file__).parent  # 개발 중엔 main.py 기준
    return base_path / relative_path

def main():
    if not acquire_singleton_lock():
        # 이미 떠 있는 인스턴스가 있음 → 그 인스턴스가 쓰고 있는 포트를 읽어서 브라우저만 열기
        if PORT_FILE.exists():
            open_browser(int(PORT_FILE.read_text().strip()))
        return

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    port = find_free_port()
    PORT_FILE.write_text(str(port))  # 다음 실행 때(또는 트레이 메뉴에서) 참고용

    config = ensure_config()
    app = create_app(config)

    threading.Thread(target=run_server, args=(app, port), daemon=True).start()
    threading.Timer(1.0, lambda: open_browser(port)).start()

    image = Image.open(resource_path("./icon.png"))
    menu = Menu(
        MenuItem("대시보드 열기", lambda: open_browser(port)),
        MenuItem("종료", quit_app),
    )
    Icon("local-alimtalk-sender", image, "로컬 알림톡 발송기", menu).run()


if __name__ == "__main__":
    main()