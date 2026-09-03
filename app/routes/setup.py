"""
전역 설정(Solapi 연동 정보, 건물 기본 정보) 및 템플릿 조회 라우트.

GET  /api/setup    — 현재 설정 여부/값 조회 (민감정보 제외)
POST /setup        — 전역 설정 저장 (config.json)
GET  /api/template — ailmtalk.template 원문, 추출 변수 목록, 서비스별 헤더/매핑 조회
"""

from typing import Optional
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.config import is_configured
from app.services import storage, template_service

router = APIRouter()


class SetupPayload(BaseModel):
    solapi_key: Optional[str] = ""
    solapi_secret: Optional[str] = ""
    sender_phone: Optional[str] = ""


@router.post("/setup")
async def save_setup(payload: SetupPayload):
    data = payload.model_dump()
    storage.save_app_config(data)
    return {"ok": True}


@router.get("/api/setup")
async def get_setup_status():
    config = storage.get_app_config()

    return {
        "configured": is_configured(config),
        "sender_phone": config.get("sender_phone") or "",
        # solapi_key / solapi_secret은 절대 프론트로 내려보내지 않는다.
    }


@router.get("/api/template")
async def get_template_and_mapping(
    service_id: int = Query(0),
    template_id: Optional[str] = Query(None),
):
    target_tid = template_id
    if not target_tid and service_id:
        svc = storage.get_service(service_id)
        if svc:
            target_tid = svc.get("template_id")

    config = storage.get_app_config()
    template_info = template_service.load_template_info(target_tid, config)

    db_headers = storage.get_excel_headers(service_id)
    headers = db_headers if db_headers else []

    db_mapping = storage.get_template_mapping(service_id)
    mapping = db_mapping if db_mapping else {}

    return {
        "template_id": template_info.get("id", ""),
        "templateId": template_info.get("templateId") or template_info.get("id", ""),
        "template_name": template_info.get("name", ""),

        "name": template_info.get("name", ""),
        "content": template_info.get("content", ""),
        "variables": template_info.get("variables", []),
        "buttons": template_info.get("buttons") or [],
        "quickReplies": template_info.get("quickReplies") or [],
        "highlight": template_info.get("highlight"),
        "item": template_info.get("item"),
        "status": template_info.get("status"),
        "messageType": template_info.get("messageType"),
        "emphasizeType": template_info.get("emphasizeType"),
        "emphasizeTitle": template_info.get("emphasizeTitle"),
        "emphasizeSubtitle": template_info.get("emphasizeSubtitle"),
        "extra": template_info.get("extra"),
        "ad": template_info.get("ad"),
        "header": template_info.get("header"),
        "channelId": template_info.get("channelId"),
        "categoryCode": template_info.get("categoryCode"),
        "error": template_info.get("error"),
        "excel_headers": headers,
        "template_mapping": mapping,
        "raw": template_info.get("raw"),
    }


