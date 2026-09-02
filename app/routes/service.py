"""
서비스 CRUD 라우트 및 알림톡 템플릿 목록 조회.

GET    /api/templates      — 사용 가능한 알림톡 템플릿 목록 조회 (향후 외부 API 연동 대비)
GET    /api/services       — 서비스 목록 조회
GET    /api/services/{id}  — 특정 서비스 조회 (헤더·매핑·발송 주기·선택 템플릿 포함)
POST   /api/services       — 새 서비스 생성
PUT    /api/services/{id}  — 서비스 수정
DELETE /api/services/{id}  — 서비스 삭제
"""

import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.models import KakaoTemplate
from app.services import solapi_client, storage, template_service

router = APIRouter()


class ServicePayload(BaseModel):
    name: str
    description: Optional[str] = ""
    send_cycle: Optional[str] = "monthly"
    pf_id: Optional[str] = ""
    template_id: Optional[str] = ""
    excel_headers: Optional[list[str]] = None
    template_mapping: Optional[dict[str, str]] = None
    mapping_meta: Optional[dict] = None  # { varKey: {type, required, defaultValue} }


@router.get("/api/solapi/senders")
async def list_solapi_senders():
    """Solapi에 등록된 카카오 채널(발신 프로필 pfId) 목록 조회."""
    config = storage.get_app_config()
    senders = solapi_client.list_friends(config)
    return {"senders": senders}


@router.get("/api/templates")
async def list_templates(pf_id: str):
    """사용 가능한 템플릿 목록 반환 (Solapi 템플릿)."""
    config = storage.get_app_config()
    templates = solapi_client.list_solapi_templates(pf_id, config)
    return {"templates": templates}


@router.get("/api/templates/{template_id}")
async def get_template_detail(template_id: str):
    """템플릿 단건 상세 조회 (GET /kakao/v2/templates/:templateId 규격 호환)."""
    config = storage.get_app_config()
    template_info = template_service.get_template_by_id(template_id, config)
    if not template_info:
        return JSONResponse(status_code=404, content={"error": f"템플릿을 찾을 수 없습니다: {template_id}"})
    return template_info


@router.get("/api/services")
async def list_services():
    services = storage.list_services()
    return {"services": services}


@router.post("/api/services/import")
async def import_service_json(payload: dict):
    """JSON 설정을 받아 새 서비스로 생성 (외래키로 연결된 templates 테이블에 템플릿 정보 저장)."""
    name = str(payload.get("name", "")).strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "유효하지 않은 서비스 JSON 파일입니다. (이름 누락)"})

    description = str(payload.get("description", "")).strip()
    send_cycle = str(payload.get("send_cycle", "monthly")).strip()
    pf_id = str(payload.get("pf_id", "")).strip()
    template_id = str(payload.get("template_id", "")).strip()
    excel_headers = payload.get("excel_headers") or []
    template_mapping = payload.get("template_mapping") or {}
    mapping_meta = payload.get("mapping_meta") or {}

    config = storage.get_app_config()
    st = None
    if template_id:
        st = solapi_client.get_solapi_template(template_id, config)

    service_id = storage.create_service(
        name=name,
        description=description,
        send_cycle=send_cycle,
        pf_id=pf_id,
        template_id=template_id,
    )
    if st:
        storage.save_service_template(service_id, st)

    storage.save_excel_headers(excel_headers, service_id)
    storage.save_template_mapping(template_mapping, service_id, mapping_meta)

    return {"ok": True, "service_id": service_id, "name": name}


@router.post("/api/services")
async def create_service(payload: ServicePayload):
    if not payload.name.strip():
        return JSONResponse(status_code=400, content={"error": "서비스 이름은 필수 항목입니다."})

    template_id = payload.template_id or ""
    pf_id = payload.pf_id.strip() if payload.pf_id else ""

    config = storage.get_app_config()
    st = None
    if template_id:
        st = solapi_client.get_solapi_template(template_id, config)

    service_id = storage.create_service(
        name=payload.name.strip(),
        description=payload.description or "",
        send_cycle=payload.send_cycle or "monthly",
        pf_id=pf_id,
        template_id=template_id,
    )
    if st:
        storage.save_service_template(service_id, st)

    # 엑셀 헤더 저장
    headers = payload.excel_headers if payload.excel_headers else []
    storage.save_excel_headers(headers, service_id)

    # 템플릿 매핑 + 메타 저장
    mapping = payload.template_mapping if payload.template_mapping else {}
    storage.save_template_mapping(mapping, service_id, payload.mapping_meta)

    return {"ok": True, "service_id": service_id}


@router.get("/api/services/{service_id}/export")
async def export_service_json(service_id: int):
    """특정 서비스의 설정을 JSON 형식으로 추출."""
    svc = storage.get_service(service_id)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "서비스를 찾을 수 없습니다."})

    headers = storage.get_excel_headers(service_id)
    mapping = storage.get_template_mapping(service_id)
    mapping_meta = storage.get_mapping_meta(service_id)

    export_data = {
        "version": 1,
        "exported_at": storage._now(),
        "name": svc.get("name", ""),
        "description": svc.get("description", ""),
        "send_cycle": svc.get("send_cycle", "monthly"),
        "pf_id": svc.get("pf_id", ""),
        "template_id": svc.get("template_id", ""),
        "excel_headers": headers or [],
        "template_mapping": mapping or {},
        "mapping_meta": mapping_meta or {},
    }
    return export_data


@router.get("/api/services/{service_id}")
async def get_service(service_id: int):
    svc = storage.get_service(service_id)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "서비스를 찾을 수 없습니다."})

    headers = storage.get_excel_headers(service_id)
    mapping = storage.get_template_mapping(service_id)
    mapping_meta = storage.get_mapping_meta(service_id)

    # 외래키(service_id)로 templates 테이블에서 저장된 템플릿 로드
    saved_tmpl = storage.get_service_template(service_id)
    saved_date_updated = saved_tmpl.get("date_updated", "") if saved_tmpl else ""

    template_id = svc.get("template_id", "")
    config = storage.get_app_config()

    # 실시간 Solapi 템플릿 조회
    template_info = template_service.get_template_by_id(template_id, config) if template_id else None
    if not template_info:
        template_info = template_service.load_template_info(template_id, config=config)

    current_date_updated = (template_info.get("dateUpdated") or template_info.get("dateCreated") or "") if template_info else ""

    # dateUpdated 비교
    template_changed = False
    if saved_date_updated and current_date_updated and saved_date_updated >= current_date_updated:
        template_changed = True

    return {
        **svc,
        "excel_headers": headers or [],
        "template_mapping": mapping or {},
        "mapping_meta": mapping_meta or {},
        "template_id": template_id,
        "template_changed": template_changed,
        "saved_template_date_updated": saved_date_updated,
        "current_template_date_updated": current_date_updated,
        "template_content": template_info.get("content", "") or (saved_tmpl.get("content", "") if saved_tmpl else ""),
        "template_variables": template_info.get("variables", []) or (saved_tmpl.get("variables", []) if saved_tmpl else []),
        "template_buttons": template_info.get("buttons", []) or (saved_tmpl.get("buttons", []) if saved_tmpl else []),
        "template_highlight": template_info.get("highlight") or (saved_tmpl.get("highlight") if saved_tmpl else None),
        "template_item": template_info.get("item") or (saved_tmpl.get("item") if saved_tmpl else None),
        "template_status": template_info.get("status") or (saved_tmpl.get("status", "") if saved_tmpl else ""),
        "template_extra": template_info.get("extra") or (saved_tmpl.get("extra", "") if saved_tmpl else ""),
        "template_ad": template_info.get("ad") or (saved_tmpl.get("ad", "") if saved_tmpl else ""),
        "template_header": template_info.get("header") or (saved_tmpl.get("header", "") if saved_tmpl else ""),
        "template_emphasize_title": template_info.get("emphasizeTitle") or (saved_tmpl.get("emphasize_title", "") if saved_tmpl else ""),
        "template_emphasize_type": template_info.get("emphasizeType") or (saved_tmpl.get("emphasize_type", "") if saved_tmpl else ""),
    }


@router.put("/api/services/{service_id}")
async def update_service(service_id: int, payload: ServicePayload):
    svc = storage.get_service(service_id)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "서비스를 찾을 수 없습니다."})

    if not payload.name.strip():
        return JSONResponse(status_code=400, content={"error": "서비스 이름은 필수 항목입니다."})

    template_id = payload.template_id if payload.template_id is not None else svc.get("template_id", "")
    pf_id = payload.pf_id.strip() if payload.pf_id is not None else svc.get("pf_id", "")

    config = storage.get_app_config()
    st = None
    if template_id:
        st = solapi_client.get_solapi_template(template_id, config)

    storage.update_service(
        service_id=service_id,
        name=payload.name.strip(),
        description=payload.description or "",
        send_cycle=payload.send_cycle or "monthly",
        pf_id=pf_id,
        template_id=template_id,
    )

    if st:
        storage.save_service_template(service_id, st)

    if payload.excel_headers is not None:
        storage.save_excel_headers(payload.excel_headers, service_id)

    if payload.template_mapping is not None:
        storage.save_template_mapping(payload.template_mapping, service_id, payload.mapping_meta)

    return {"ok": True, "service_id": service_id}



@router.delete("/api/services/{service_id}")
async def delete_service(service_id: int):
    svc = storage.get_service(service_id)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "서비스를 찾을 수 없습니다."})

    storage.delete_service(service_id)
    return {"ok": True}

