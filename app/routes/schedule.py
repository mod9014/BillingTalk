"""
예약 발송 등록 라우트.

POST /schedule/check-duplicates — 발송 예정일 및 현재 업로드 데이터 기준 중복 발송 여부 사전 검사
POST /schedule                  — 미리보기 데이터 중 유효 행 예약발송 등록 및 주기 키 기록
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.models import BillingRow
from app.routes.upload import get_draft_rows
from app.services import excel_parser, formula_evaluator, storage, template_service
from app.services.solapi_client import SolapiError, send_reserved

router = APIRouter()


class DuplicateCheckPayload(BaseModel):
    scheduled_date: str
    service_id: int = 0
    cycle_key: Optional[str] = None


class SchedulePayload(BaseModel):
    scheduled_date: str  # "YYYY-MM-DD"
    scheduled_time: Optional[str] = None  # "HH:MM"
    service_id: Optional[int] = 0
    cycle_key: Optional[str] = None
    force: Optional[bool] = False  # 중복 경고 후 사용자가 강제 등록을 승인한 경우
    rows: Optional[list[list[str]]] = None  # 테이블에서 직접 편집/수정된 데이터가 전달될 경우 사용


def _extract_units_from_draft(raw_rows: list[list[str]], mapping: dict[str, str]) -> list[str]:
    """draft_rows에서 호실 목록을 추출한다."""
    if not raw_rows or len(raw_rows) < 2:
        return []

    headers = [str(h).strip() for h in raw_rows[0]]
    unit_map_val = mapping.get("호실", "{호실}").replace("{", "").replace("}", "").strip()

    # 헤더 인덱스 찾기
    unit_idx = -1
    for idx, h in enumerate(headers):
        if h == unit_map_val or h in ("호실", "호수", "호실번호"):
            unit_idx = idx
            break

    if unit_idx == -1 and len(headers) > 0:
        unit_idx = 0  # 기본 첫 번째 컬럼 가정

    units = []
    for r in raw_rows[1:]:
        if len(r) > unit_idx and r[unit_idx]:
            val = str(r[unit_idx]).strip()
            if val:
                units.append(val)
    return units


@router.post("/schedule/check-duplicates")
async def check_duplicate_schedule(payload: DuplicateCheckPayload):
    service_id = payload.service_id or 0
    raw_rows = get_draft_rows(service_id)
    if not raw_rows or len(raw_rows) < 2:
        return JSONResponse(status_code=400, content={"error": "검사할 데이터가 없습니다. 먼저 업로드해주세요."})

    mapping = storage.get_template_mapping(service_id)
    target_units = _extract_units_from_draft(raw_rows, mapping)

    result = storage.check_duplicates(
        service_id=service_id,
        scheduled_date=payload.scheduled_date,
        target_units=target_units,
        explicit_cycle_key=payload.cycle_key,
    )
    return result


@router.post("/schedule")
async def register_schedule(payload: SchedulePayload):
    config = storage.get_app_config()
    service_id = payload.service_id or 0

    raw_rows = get_draft_rows(service_id)
    if not raw_rows or len(raw_rows) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "발송 가능한 유효 데이터가 없습니다. 먼저 업로드/붙여넣기로 데이터를 확인해주세요."},
        )

    try:
        target_date = datetime.strptime(payload.scheduled_date[:10], "%Y-%m-%d")
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "발송 예정일 형식이 올바르지 않습니다."})

    year, month = target_date.year, target_date.month

    # 2D 배열 형태의 raw_rows를 파싱하여 BillingRow 객체 및 템플릿 변수 생성
    mapping = storage.get_template_mapping(service_id)
    headers = [str(h).strip() for h in raw_rows[0]]

    # 발송 예정 시간 (payload 우선, 없으면 mapping 설정값, 기본 09:00)
    send_time_val = str(payload.scheduled_time or mapping.get("send_time", "09:00")).strip()
    if ":" in send_time_val:
        parts = send_time_val.split(":")
        hh = parts[0].strip().zfill(2)
        mm = parts[1].strip().zfill(2)
    elif send_time_val.isdigit():
        hh = send_time_val.zfill(2)
        mm = "00"
    else:
        hh, mm = "09", "00"
    scheduled_str = target_date.strftime(f"%Y-%m-%d {hh}:{mm}:00")

    # 발송 주기 키 결정 (프론트엔드 명시 cycle_key 우선)
    svc = storage.get_service(service_id)
    send_cycle = svc["send_cycle"] if svc else "monthly"
    if payload.cycle_key:
        cycle_key = payload.cycle_key
        _, cycle_label = storage.compute_cycle_key(payload.scheduled_date, send_cycle)
    else:
        cycle_key, cycle_label = storage.compute_cycle_key(payload.scheduled_date, send_cycle)

    # 템플릿 정보 및 매핑 로드
    template_id = svc.get("template_id", "") if svc else ""
    template_info = template_service.load_template_info(template_id, config)
    template_vars = template_info.get("variables", [])

    mapping = storage.get_template_mapping(service_id)
    mapping_meta = storage.get_mapping_meta(service_id)

    # 유효 행 변환
    billing_rows = []
    template_vars_list = []

    for r in raw_rows[1:]:
        row_dict = {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}

        # 1. 수신 연락처 동적 평가 (phone 매핑 수식 적용)
        phone_expr = mapping.get("phone", "{연락처}")
        phone_val = formula_evaluator.evaluate_expression(
            expr=phone_expr,
            row_dict=row_dict,
            config=config,
            year=year,
            month=month,
            field_type="phone",
        )

        # 2. 식별자 (unit, tenant_name) 유연 추출
        unit_expr = mapping.get("호실", "{호실}")
        unit_val = formula_evaluator.evaluate_expression(
            expr=unit_expr, row_dict=row_dict, config=config, year=year, month=month
        ) or str(row_dict.get("호실", "") or (r[0] if len(r) > 0 else "")).strip()

        tenant_key = next((k for k, v in mapping_meta.items() if v.get("type") == "name"))
        tenant_expr = mapping.get(tenant_key, "{입주자명}")
        tenant_val = formula_evaluator.evaluate_expression(
            expr=tenant_expr, row_dict=row_dict, config=config, year=year, month=month
        )

        tvars = excel_parser.evaluate_row_template_vars(
            row_dict=row_dict,
            mapping=mapping,
            mapping_meta=mapping_meta,
            config=config,
            year=year,
            month=month,
            template_vars=template_vars,
        )

        billing_row = BillingRow(
            phone=str(phone_val),
            unit=str(unit_val),
            tenant_name=str(tenant_val),
            valid=bool(phone_val),
            data=row_dict,
        )
        billing_rows.append(billing_row)
        template_vars_list.append(tvars)

    valid_rows = [r for r in billing_rows if r.valid]
    valid_tvars = [t for r, t in zip(billing_rows, template_vars_list) if r.valid]

    if not valid_rows:
        return JSONResponse(
            status_code=400,
            content={"error": "유효한 수신 연락처가 있는 행이 없습니다."},
        )

    # 서비스별 지정된 발신 프로필(pfId) 및 템플릿ID 주입
    send_config = dict(config)
    if svc:
        if svc.get("pf_id"):
            send_config["solapi_sender"] = svc["pf_id"]
        if svc.get("template_id"):
            send_config["template_id"] = svc["template_id"]

    try:
        results = send_reserved(valid_rows, valid_tvars, scheduled_str, send_config)
    except SolapiError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    storage.save_send_batch(
        rows=valid_rows,
        template_vars_list=valid_tvars,
        results=results,
        year=year,
        month=month,
        service_id=service_id,
        cycle_key=cycle_key,
    )

    return {
        "registeredCount": len(results),
        "scheduledDate": scheduled_str,
        "cycleKey": cycle_key,
        "cycleLabel": cycle_label,
    }
