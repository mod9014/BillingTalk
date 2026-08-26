"""
서비스 CRUD 라우트 및 알림톡 템플릿 목록 조회.

GET    /api/templates      — 사용 가능한 알림톡 템플릿 목록 조회 (향후 외부 API 연동 대비)
GET    /api/services       — 서비스 목록 조회
GET    /api/services/{id}  — 특정 서비스 조회 (헤더·매핑·발송 주기·선택 템플릿 포함)
POST   /api/services       — 새 서비스 생성
PUT    /api/services/{id}  — 서비스 수정
DELETE /api/services/{id}  — 서비스 삭제
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import DEFAULT_EXCEL_HEADERS, DEFAULT_TEMPLATE_MAPPING
from app.services import solapi_client, storage, template_service

router = APIRouter()


class ServicePayload(BaseModel):
    name: str
    description: Optional[str] = ""
    send_cycle: Optional[str] = "monthly"
    pf_id: Optional[str] = ""
    template_id: Optional[str] = "local_default"
    excel_headers: Optional[list[str]] = None
    template_mapping: Optional[dict[str, str]] = None
    mapping_meta: Optional[dict] = None  # { varKey: {type, required, defaultValue} }


@router.get("/api/solapi/senders")
async def list_solapi_senders(request: Request):
    """Solapi에 등록된 카카오 채널(발신 프로필 pfId) 목록 조회."""
    config = request.app.state.config or {}
    senders = solapi_client.list_plus_friends(config)
    return {"senders": senders}


@router.get("/api/templates")
async def list_templates(request: Request, pf_id: Optional[str] = ""):
    """사용 가능한 템플릿 목록 반환 (로컬 템플릿 + pf_id가 주어진 경우 Solapi 템플릿 포함)."""
    templates = template_service.list_templates()
    config = request.app.state.config or {}

    # pf_id가 있으면 Solapi 템플릿도 가져와 합산
    if pf_id and config.get("solapi_key"):
        solapi_tmps = solapi_client.list_solapi_templates(pf_id, config)
        for st in solapi_tmps:
            t_id = st.get("templateId") or st.get("id")
            t_name = st.get("name") or t_id
            if t_id:
                templates.append({
                    "id": t_id,
                    "title": f"[Solapi] {t_name}",
                    "content": st.get("content", ""),
                    "is_local": False,
                })

    return {"templates": templates}


@router.get("/api/services")
async def list_services():
    services = storage.list_services()
    return {"services": services}


@router.post("/api/services/import")
async def import_service_json(payload: dict):
    """JSON 설정을 받아 새 서비스로 생성."""
    name = str(payload.get("name", "")).strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "유효하지 않은 서비스 JSON 파일입니다. (이름 누락)"})

    description = str(payload.get("description", "")).strip()
    send_cycle = str(payload.get("send_cycle", "monthly")).strip()
    pf_id = str(payload.get("pf_id", "")).strip()
    template_id = str(payload.get("template_id", "local_default")).strip() or "local_default"
    excel_headers = payload.get("excel_headers") or DEFAULT_EXCEL_HEADERS
    template_mapping = payload.get("template_mapping") or DEFAULT_TEMPLATE_MAPPING
    mapping_meta = payload.get("mapping_meta") or {}

    service_id = storage.create_service(
        name=name,
        description=description,
        send_cycle=send_cycle,
        pf_id=pf_id,
        template_id=template_id,
    )
    storage.save_excel_headers(excel_headers, service_id)
    storage.save_template_mapping(template_mapping, service_id, mapping_meta)

    return {"ok": True, "service_id": service_id, "name": name}


@router.post("/api/services")
async def create_service(payload: ServicePayload):
    if not payload.name.strip():
        return JSONResponse(status_code=400, content={"error": "서비스 이름은 필수 항목입니다."})

    template_id = payload.template_id or "local_default"
    pf_id = payload.pf_id.strip() if payload.pf_id else ""

    service_id = storage.create_service(
        name=payload.name.strip(),
        description=payload.description or "",
        send_cycle=payload.send_cycle or "monthly",
        pf_id=pf_id,
        template_id=template_id,
    )

    # 엑셀 헤더 저장
    headers = payload.excel_headers if payload.excel_headers else DEFAULT_EXCEL_HEADERS
    storage.save_excel_headers(headers, service_id)

    # 템플릿 매핑 + 메타 저장
    mapping = payload.template_mapping if payload.template_mapping else DEFAULT_TEMPLATE_MAPPING
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
        "template_id": svc.get("template_id", "local_default"),
        "excel_headers": headers if headers else DEFAULT_EXCEL_HEADERS,
        "template_mapping": mapping if mapping else DEFAULT_TEMPLATE_MAPPING,
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

    # 서비스에 지정된 템플릿 로드
    template_id = svc.get("template_id", "local_default")
    template_info = template_service.get_template_by_id(template_id)
    if not template_info:
        template_info = template_service.load_template_info()

    return {
        **svc,
        "excel_headers": headers if headers else DEFAULT_EXCEL_HEADERS,
        "template_mapping": mapping if mapping else DEFAULT_TEMPLATE_MAPPING,
        "mapping_meta": mapping_meta,
        "template_id": template_id,
        "template_content": template_info.get("content", ""),
        "template_variables": template_info.get("variables", []),
    }


@router.put("/api/services/{service_id}")
async def update_service(service_id: int, payload: ServicePayload):
    svc = storage.get_service(service_id)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "서비스를 찾을 수 없습니다."})

    if not payload.name.strip():
        return JSONResponse(status_code=400, content={"error": "서비스 이름은 필수 항목입니다."})

    template_id = payload.template_id or svc.get("template_id", "local_default")
    pf_id = payload.pf_id.strip() if payload.pf_id is not None else svc.get("pf_id", "")

    storage.update_service(
        service_id=service_id,
        name=payload.name.strip(),
        description=payload.description or "",
        send_cycle=payload.send_cycle or "monthly",
        pf_id=pf_id,
        template_id=template_id,
    )

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
