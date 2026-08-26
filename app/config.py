"""
로컬 설정 파일(~/.officetel-bill/config.json) 로드/저장.

주의:
  - solapi_key, solapi_secret은 절대 소스코드에 하드코딩하지 않는다.
  - 이 파일은 사용자 홈 디렉토리에 저장되며 저장소에는 포함되지 않는다 (.gitignore 참고).
"""

from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".officetel-bill"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_EXCEL_HEADERS = [
    "호실",
    "입주자명",
    "연락처",
    "임대료",
    "일반관리비",
    "주차료",
    "기타",
    "전기료",
    "수도료",
    "TV수신료",
    "전월미납금",
    "납기내금액",
    "납기후금액",
    "총금액",
    "납부기한",
]

DEFAULT_TEMPLATE_MAPPING = {
    "phone": "{연락처}",
    "send_date": "{납부기한} - 5",
    "send_time": "09:00",
    "호실": "{호실}",
    "입주자명": "{입주자명}",
    "임대료": "{임대료}",
    "일반관리비": "{일반관리비}",
    "주차료": "{주차료}",
    "기타": "{기타}",
    "전기료": "{전기료}",
    "수도료": "{수도료}",
    "TV수신료": "{TV수신료}",
    "전월미납금": "{전월미납금}",
    "납기내금액": "{납기내금액}",
    "납기후금액": "{납기후금액}",
    "총금액": "{총금액}",
    "납부기한": "{납부기한}",
    "청구년": "__system_year__",
    "청구월": "__system_month__",
    "오피스텔명": "__config_building_name__",
    "관리소연락처": "__config_office_phone__",
}

DEFAULT_CONFIG = {
    "solapi_key": "",
    "solapi_secret": "",
    "solapi_sender": "",   # 카카오 채널 발신 프로필 ID (pfId)
    "sender_phone": "",    # 발신번호 (SMS 대체발송용, 등록된 발신번호)
    "template_id": "",     # 알림톡 템플릿 ID
    "building_name": "",   # #{오피스텔명}
    "office_phone": "",    # #{관리소연락처}
    "excel_headers": DEFAULT_EXCEL_HEADERS,
    "template_mapping": DEFAULT_TEMPLATE_MAPPING,
}


def ensure_config() -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return {**DEFAULT_CONFIG, **loaded}
        except Exception as e:
            print(f"⚠️ config.json 읽기 실패, 기본값 사용: {e}")

    # 최초 실행 혹은 설정 파일 없음
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)
    existing = ensure_config()
    merged = {**DEFAULT_CONFIG, **existing, **config}
    # 비밀 키가 빈 문자열로 넘어온 경우 기존 값 유지
    if not config.get("solapi_key") and existing.get("solapi_key"):
        merged["solapi_key"] = existing["solapi_key"]
    if not config.get("solapi_secret") and existing.get("solapi_secret"):
        merged["solapi_secret"] = existing["solapi_secret"]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def is_configured(config: dict) -> bool:
    required = ("solapi_key", "solapi_secret", "solapi_sender", "template_id")
    return all(config.get(k) for k in required)

