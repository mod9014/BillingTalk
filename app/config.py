"""
로컬 설정 파일(~/.officetel-bill/config.json) 로드/저장.

주의:
  - solapi_key, solapi_secret은 절대 소스코드에 하드코딩하지 않는다.
  - 이 파일은 사용자 홈 디렉토리에 저장되며 저장소에는 포함되지 않는다 (.gitignore 참고).
"""

from pathlib import Path
import json

from app.services import storage

DEFAULT_CONFIG = {
    "solapi_key": "",
    "solapi_secret": "",
    "sender_phone": "",
}


def ensure_config() -> dict:
    """DB에서 전역 설정 조회."""
    return storage.get_app_config()


def save_config(config: dict) -> dict:
    """DB에 전역 설정 저장."""
    return storage.save_app_config(config)


def is_configured(config: dict | None = None) -> bool:
    """Solapi API Key & Secret 설정 여부 확인."""
    if config is None:
        config = storage.get_app_config()
    required = ("solapi_key", "solapi_secret")
    return all(bool(config.get(k)) for k in required)

