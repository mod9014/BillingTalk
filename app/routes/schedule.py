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
from app.services.solapi_client import SolapiError, cancel_reserved, send_reserved

router = APIRouter()


class DuplicateCheckPayload(BaseModel):
    scheduled_date: str
    service_id: int = 0
    cycle_key: Optional[str] = None


class SchedulePayload(BaseModel):
    scheduled_date: str  # "YYYY-MM-DD"
    scheduled_time: str = "09:00"  # "HH:MM"
    service_id: int
    cycle_key: Optional[str] = None
    force: Optional[bool] = False  # 중복 경고 후 사용자가 강제 등록을 승인한 경우
    headers: Optional[list[str]] = None 
    header_vars: list[str]
    rows: list[list[str]]


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
    mapping_meta = storage.get_mapping_meta(service_id)

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
    scheduled_str = target_date.strftime(f"%Y-%m-%dT{hh}:{mm}:00+09:00")

    # 발송 주기 키 결정 (프론트엔드 명시 cycle_key 우선)
    svc = storage.get_service(service_id)
    send_cycle = svc["send_cycle"] if svc else "monthly"
    if payload.cycle_key:
        cycle_key = payload.cycle_key
        _, cycle_label = storage.compute_cycle_key(payload.scheduled_date, send_cycle)
    else:
        cycle_key, cycle_label = storage.compute_cycle_key(payload.scheduled_date, send_cycle)

    unit_var = ["호실", "호수", "호실번호","호"]
    requared_header = ["send_date","send_time","phone", "unit"]
    
    # 유효 행 변환
    billing_rows = []
    for row in payload.rows:
        row_dict_by_var: dict[str, str] = {}
        requared_val: dict[str, str] = {}
        for var_name, val in zip(payload.header_vars, row):
            if var_name in requared_header:
                requared_val[var_name] = val
                continue
            if var_name.startswith("#{") and var_name.endswith("}"):
                row_dict_by_var[var_name] = val
            else:
                row_dict_by_var["#{"+var_name+"}"] = val

        if not requared_val.get("unit"):
            for var in unit_var:
                if "#{"+var+"}" in row_dict_by_var:
                    requared_val["unit"] = row_dict_by_var["#{"+var+"}"]
                    break
        send_date_val = str(requared_val.get("send_date") or "").strip()
        send_time_val = str(requared_val.get("send_time") or mapping.get("send_time", "09:00") or "09:00").strip()

        # send_date가 비어있으면 payload.scheduled_date 사용
        if not send_date_val or send_date_val == "":
            send_date_val = payload.scheduled_date[:10]

        # 날짜 정규화: YYYY-MM-DD 형식 맞추기
        try:
            sd = datetime.strptime(send_date_val[:10], "%Y-%m-%d")
            send_date_str = sd.strftime("%Y-%m-%d")
        except ValueError:
            send_date_str = payload.scheduled_date[:10]

        # 시간 정규화: HH:MM
        if ":" in send_time_val:
            parts = send_time_val.split(":")
            t_hh = parts[0].strip().zfill(2)
            t_mm = parts[1].strip().zfill(2)
        elif send_time_val.isdigit():
            t_hh = send_time_val.zfill(2)
            t_mm = "00"
        else:
            t_hh, t_mm = "09", "00"

        send_date = f"{send_date_str}T{t_hh}:{t_mm}:00+09:00"


        billing_row = BillingRow(
            phone=str(requared_val.get("phone")),
            unit=str(requared_val.get("unit")),
            send_date=str(send_date),
            valid=bool(requared_val.get("phone")),
            data=row_dict_by_var,
        )
        billing_rows.append(billing_row)

    valid_rows = [r for r in billing_rows if r.valid]

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

    # send_date + send_time 기준으로 그룹화하여 각 그룹을 별도 예약 발송
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for row in valid_rows:
        groups[row.send_date].append(row)

    all_results: list = []
    first_scheduled_str = scheduled_str
    try:
        for group_scheduled_str, group_rows in groups.items():
            grp_scheduled_str = group_scheduled_str
            if first_scheduled_str == scheduled_str:
                first_scheduled_str = grp_scheduled_str

            grp_results = send_reserved(group_rows, grp_scheduled_str, send_config)
            all_results.extend(grp_results)

            storage.save_send_batch(
                rows=group_rows,
                results=grp_results,
                year=year,
                month=month,
                service_id=service_id,
                cycle_key=cycle_key,
            )
    except SolapiError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    return {
        "registeredCount": len(all_results),
        "scheduledDate": first_scheduled_str,
        "groupCount": len(groups),
        "cycleKey": cycle_key,
        "cycleLabel": cycle_label,
    }

@router.post("/cancel-schedule")
async def cancel_schedule(group_ids: list[str]):
    config = storage.get_app_config()
    if not group_ids:
        return {"ok": True, "cancelled_count": 0}

    all_results: list = []
    try:
        for group_id in group_ids:
            if not group_id:
                continue
            result = cancel_reserved(group_id, config)
            all_results.append(result)
        if all_results:
            storage.update_send_status(all_results)
    except SolapiError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"예약 취소 처리 중 오류: {e}"})

    return {"ok": True, "cancelled_count": len(all_results)}
    