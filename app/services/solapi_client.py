"""
Solapi API 래퍼. API 키는 이 모듈 안에서만 사용하고 프론트엔드로 절대 넘기지 않는다.

send_reserved(rows, template_vars_list, scheduled_date, config) -> list[SendResult]
    카카오 알림톡 예약발송 등록 (POST /messages/v4/send-many/detail)
get_status(group_id) -> list[SendResult]
    발송 그룹의 최신 상태 조회 (폴링용, GET /messages/v4/list-old)

참고: https://developers.solapi.dev (send-many/detail, list-old)
NOTE: statusCode 등 응답 필드의 실제 값은 Solapi 키 발급 후 1회 테스트 발송으로 검증 필요.
      (storage.py의 SUCCESS_CODES / FAILURE_CODES 참고)
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

import requests

from app.models import BillingRow, SendResult

BASE_URL = "https://api.solapi.com"
SEND_URL = f"{BASE_URL}/messages/v4/send-many/detail"
LIST_URL = f"{BASE_URL}/messages/v4/list-old"

TIMEOUT_SEC = 15


class SolapiError(RuntimeError):
    pass


def _auth_header(api_key: str, api_secret: str) -> dict:
    """HMAC-SHA256 서명 헤더 생성. (date + salt를 secret으로 서명)"""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    salt = uuid.uuid4().hex
    signature = hmac.new(
        api_secret.encode("utf-8"),
        (date + salt).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "Authorization": (
            f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}"
        ),
        "Content-Type": "application/json; charset=utf-8",
    }


def _require_config(config: dict) -> None:
    missing = [k for k in ("solapi_key", "solapi_secret", "solapi_sender", "template_id") if not config.get(k)]
    if missing:
        raise SolapiError(f"Solapi 설정이 누락되었습니다: {', '.join(missing)} (설정 화면에서 입력해주세요)")


def send_reserved(
    rows: list[BillingRow],
    template_vars_list: list[dict],
    scheduled_date: str,
    config: dict,
) -> list[SendResult]:
    """알림톡 예약발송 등록. scheduled_date: 'YYYY-MM-DD HH:MM:SS' 형식.
    disableSms=False로 알림톡 실패 시 SMS 자동 대체발송 유지."""
    _require_config(config)

    messages = []
    for row, tvars in zip(rows, template_vars_list):
        messages.append({
            "to": row.phone,
            "from": config.get("sender_phone") or config["solapi_sender"],
            "kakaoOptions": {
                "pfId": config["solapi_sender"],
                "templateId": config["template_id"],
                "variables": tvars,
                "disableSms": False,
            },
            "customFields": {"unit": row.unit},
        })

    payload = {
        "messages": messages,
        "scheduledDate": scheduled_date,
        "showMessageList": True,
        "allowDuplicates": False,
    }

    headers = _auth_header(config["solapi_key"], config["solapi_secret"])

    try:
        resp = requests.post(SEND_URL, headers=headers, json=payload, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        raise SolapiError(f"Solapi 요청 실패: {e}") from e

    if resp.status_code >= 400:
        raise SolapiError(f"Solapi 오류 응답 ({resp.status_code}): {resp.text}")

    body = resp.json()
    group_id = (body.get("groupInfo") or {}).get("groupId") or body.get("groupId")
    message_list = body.get("messageList") or {}

    results: list[SendResult] = []
    if isinstance(message_list, dict) and message_list:
        # {messageId: {...}} 형태 (list-old와 동일 포맷으로 반환되는 것으로 추정)
        for message_id, info in message_list.items():
            results.append(SendResult(
                message_id=message_id,
                group_id=group_id,
                to=info.get("to", ""),
                status_code=info.get("statusCode"),
                status_message=info.get("statusMessage"),
                date_processed=info.get("dateProcessed"),
            ))
    else:
        # 응답에 개별 메시지 목록이 없으면 groupId만으로 대기 상태 기록 (다음 폴링에서 get_status로 채움)
        for row in rows:
            results.append(SendResult(
                message_id=None,
                group_id=group_id,
                to=row.phone,
                status_code=None,
                status_message="예약 등록됨 (상태 확인 대기)",
                date_processed=None,
            ))

    return results


def get_status(group_id: str, config: dict) -> list[SendResult]:
    """폴링용 상태 조회. group_id에 속한 메시지들의 최신 상태를 가져온다."""
    _require_config(config)
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])

    try:
        resp = requests.get(
            LIST_URL, headers=headers, params={"groupId": group_id, "limit": 500}, timeout=TIMEOUT_SEC
        )
    except requests.RequestException as e:
        raise SolapiError(f"Solapi 상태 조회 실패: {e}") from e

    if resp.status_code >= 400:
        raise SolapiError(f"Solapi 오류 응답 ({resp.status_code}): {resp.text}")

    body = resp.json()
    message_list = body.get("messageList") or {}

    results: list[SendResult] = []
    for message_id, info in message_list.items():
        results.append(SendResult(
            message_id=message_id,
            group_id=group_id,
            to=info.get("to", ""),
            status_code=info.get("statusCode"),
            status_message=info.get("statusMessage"),
            date_processed=info.get("dateProcessed"),
        ))
    return results


def list_plus_friends(config: dict) -> list[dict]:
    """등록된 카카오톡 채널(발신 프로필 pfId) 목록 조회."""
    if not config.get("solapi_key") or not config.get("solapi_secret"):
        return []
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    url = f"{BASE_URL}/kakao/v1/plus-friends"
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("plusFriends", [])
    except Exception:
        pass
    return []


def list_solapi_templates(pf_id: str, config: dict) -> list[dict]:
    """특정 발신 프로필(pfId)에 등록된 알림톡 템플릿 목록 조회."""
    if not config.get("solapi_key") or not config.get("solapi_secret") or not pf_id:
        return []
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    url = f"{BASE_URL}/kakao/v1/templates"
    try:
        resp = requests.get(url, headers=headers, params={"pfId": pf_id}, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("templates", [])
    except Exception:
        pass
    return []
