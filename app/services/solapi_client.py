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
LIST_URL = f"{BASE_URL}/messages/v4/list"

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
    missing = [k for k in ("solapi_key", "solapi_secret") if not config.get(k)]
    if missing:
        raise SolapiError(f"Solapi 설정이 누락되었습니다: {', '.join(missing)} (설정 화면에서 입력해주세요)")


def send_reserved(
    rows: list[BillingRow],
    scheduled_date: str,
    config: dict,
    is_test: bool = False,
) -> list[SendResult]:
    """알림톡 예약발송 등록. scheduled_date: 'YYYY-MM-DD HH:MM:SS' 형식.
    disableSms=False로 알림톡 실패 시 SMS 자동 대체발송 유지."""
    _require_config(config)

    messages = []
    for row in rows:
        messages.append({
            "to": row.phone,
            "from": config.get("sender_phone") or config["solapi_sender"],
            "kakaoOptions": {
                "pfId": config["solapi_sender"],
                "templateId": config["template_id"],
                "variables": row.data,
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

    if is_test:
        raise Exception("테스트 발송입니다." + str(payload))

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
    for info in message_list:
            results.append(SendResult(
                message_id=info.get("messageId"),
                group_id=group_id,
                to=info.get("customFields").get("unit"),
                status_code=info.get("statusCode"),
                status_message=info.get("statusMessage"),
                date_processed=info.get("dateProcessed"),
            ))

    return results

def cancel_reserved(group_id: str, config: dict):
    _require_config(config)
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    try:
        resp = requests.delete(f"{BASE_URL}/messages/v4/groups/{group_id}/schedule", headers=headers, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        raise SolapiError(f"Solapi 요청 실패: {e}") from e
    
    if resp.status_code >= 400:
        raise SolapiError(f"Solapi 오류 응답 ({resp.status_code}): {resp.text}")

    body = resp.json()
    group_id = (body.get("groupInfo") or {}).get("groupId") or body.get("groupId")

    return SendResult(
                message_id="",
                group_id=group_id,
                to="",
                status_code="1070",
                status=body.get("status"),
                status_message=body.get("log")[-1].get("message"),
                date_processed=body.get("dateProcessed"),
            )

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
            status=info.get("status"),
            status_message=info.get("reason"),
            date_processed=info.get("dateProcessed"),
        ))
    return results


def list_friends(config: dict) -> list[dict]:
    """등록된 카카오톡 채널(발신 프로필 pfId / channelId) 목록 조회."""
    if not config.get("solapi_key") or not config.get("solapi_secret"):
        return []
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    url = f"{BASE_URL}/kakao/v1/plus-friends"
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("friends", [])
    except Exception as e:
        print(f"Solapi 발신 프로필 목록 조회 실패: {e}")
    return []


def get_solapi_template(template_id: str, config: dict) -> dict | None:
    """Solapi 카카오 알림톡 템플릿 단건 상세 조회 (GET /kakao/v2/templates/:templateId)."""
    if not config.get("solapi_key") or not config.get("solapi_secret") or not template_id:
        return None
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    url = f"{BASE_URL}/kakao/v2/templates/{template_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 400:
            err_msg = resp.text
            try:
                err_data = resp.json()
                err_msg = err_data.get("errorMessage") or err_data.get("message") or resp.text
            except Exception:
                pass
            raise SolapiError(
                f"Solapi API 인증/요청 오류 ({resp.status_code}: {err_msg}). "
                f"API 키가 올바르지 않거나 만료되었을 수 있습니다. 웹 [시스템 설정] 페이지에서 Solapi API Key와 API Secret을 재설정해주세요."
            )
        elif resp.status_code != 404:
            # v1 엔드포인트 fallback 시도
            fallback_url = f"{BASE_URL}/kakao/v1/templates/{template_id}"
            fb_resp = requests.get(fallback_url, headers=headers, timeout=TIMEOUT_SEC)
            if fb_resp.status_code == 200:
                return fb_resp.json()
    except Exception as e:
        print(f"Solapi 템플릿 단건 조회 실패 ({template_id}): {e}")
    return None


def list_solapi_templates(pf_id: str, config: dict) -> list[dict]:
    """특정 발신 프로필(pfId / channelId)에 등록된 알림톡 템플릿 목록 조회."""
    if not config.get("solapi_key") or not config.get("solapi_secret") or not pf_id:
        return []
    headers = _auth_header(config["solapi_key"], config["solapi_secret"])
    
    # 1. v2 템플릿 목록 조회 시도
    v2_url = f"{BASE_URL}/kakao/v2/templates"
    try:
        resp = requests.get(v2_url, headers=headers, params={"channelId": pf_id}, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("templateList") or data.get("templates") or data.get("items") or []
    except Exception as e:
        print(f"Solapi v2 템플릿 목록 조회 실패: {e}")

    # 2. v1 템플릿 목록 조회 fallback
    v1_url = f"{BASE_URL}/kakao/v1/templates"
    try:
        resp = requests.get(v1_url, headers=headers, params={"pfId": pf_id}, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("templateList") or data.get("templates") or []
    except Exception as e:
        print(f"Solapi v1 템플릿 목록 조회 실패: {e}")

    return []

