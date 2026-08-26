"""
엑셀 업로드 및 (엑셀 셀 복사→붙여넣기) 텍스트 업로드, 매핑 결과 미리보기.

POST /upload                — 엑셀 파일(.xlsx) 업로드
POST /upload/paste           — 엑셀에서 복사한 셀 범위를 그대로 붙여넣은 텍스트(TSV) 업로드
GET  /upload/preview         — 원본 업로드 데이터 조회
GET  /upload/mapped-preview  — 선택된 서비스의 템플릿 변수 기준으로 매핑 평가된 미리보기 데이터 조회
"""

from typing import Optional
from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import excel_parser, formula_evaluator, storage, template_service

router = APIRouter()

# 서비스별 최근 업로드 결과를 프로세스 메모리에 보관한다.
# 키: service_id (int), 값: list[list[str]]
_draft_rows_by_service: dict[int, list[list[str]]] = {}


class PastePayload(BaseModel):
    text: str
    service_id: int = 0


@router.post("/upload")
async def upload_excel(file: UploadFile = File(...), service_id: int = Query(0)):
    content = await file.read()
    try:
        rows = excel_parser.parse_excel(content, service_id=service_id)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"엑셀 파일을 읽을 수 없습니다: {e}"})

    if not rows:
        return JSONResponse(status_code=400, content={"error": "엑셀에서 읽은 데이터가 없습니다."})

    _draft_rows_by_service[service_id] = rows
    return rows


@router.post("/upload/paste")
async def upload_paste(payload: PastePayload):
    service_id = payload.service_id
    try:
        rows = excel_parser.parse_pasted_text(payload.text, service_id=service_id)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    if not rows:
        return JSONResponse(status_code=400, content={"error": "붙여넣은 내용에서 데이터를 찾지 못했습니다."})

    _draft_rows_by_service[service_id] = rows
    return rows


@router.get("/upload/preview")
async def get_preview(service_id: int = Query(0)):
    return _draft_rows_by_service.get(service_id, [])


@router.get("/upload/mapped-preview")
async def get_mapped_preview(
    service_id: int = Query(0),
    year: Optional[int] = Query(0),
    month: Optional[int] = Query(0),
):
    """선택된 서비스의 템플릿 변수를 테이블 헤더로 하고 매핑 평가된 셀 값들을 반환."""
    config = storage.get_app_config()
    raw_rows = _draft_rows_by_service.get(service_id, [])
    if not raw_rows or len(raw_rows) < 2:
        return {"headers": [], "header_vars": [], "rows": [], "total": 0}

    # 서비스 정보 및 템플릿 로드
    svc = storage.get_service(service_id)
    template_id = svc.get("template_id", "local_default") if svc else "local_default"
    template_info = template_service.load_template_info(template_id)
    template_vars = template_info.get("variables", [])
    mapping = storage.get_template_mapping(service_id)
    mapping_meta = storage.get_mapping_meta(service_id)  # { varKey: {type, required, defaultValue} }

    # 1. 테이블 헤더 정의
    # 발송 예정일 + 필수 수신 연락처 + 템플릿 변수들
    header_vars = ["send_date", "phone"] + [v for v in template_vars if v not in ("phone", "send_date")]
    display_headers = ["발송일", "수신 연락처"] + [f"#{v}" for v in template_vars if v not in ("phone", "send_date")]

    # 2. 엑셀 원본 헤더 인덱싱
    raw_headers = [str(h).strip() for h in raw_rows[0]]

    mapped_rows = []
    for row in raw_rows[1:]:
        row_dict = {raw_headers[i]: (row[i] if i < len(row) else "") for i in range(len(raw_headers))}

        evaluated_cells = []
        for var_name in header_vars:
            expr = mapping.get(var_name, "")
            if not expr:
                # 기본 추정
                if var_name == "send_date":
                    expr = mapping.get("발송일", "{납부기한} - 5")
                elif var_name == "phone":
                    expr = mapping.get("연락처", "{연락처}")
                else:
                    expr = f"{{{var_name}}}"

            meta = mapping_meta.get(var_name, {})
            field_type = meta.get("type", "date" if var_name == "send_date" else "text")

            val = formula_evaluator.evaluate_expression(
                expr=expr,
                row_dict=row_dict,
                config=config,
                year=year,
                month=month,
                field_type=field_type,
                is_date_field=(var_name == "send_date"),
            )
            if var_name == "phone" and not val:
                evaluated_cells = []
                break
            evaluated_cells.append(val)

        if evaluated_cells:
            mapped_rows.append(evaluated_cells)

    return {
        "headers": display_headers,
        "header_vars": header_vars,
        "rows": mapped_rows,
        "total": len(mapped_rows),
        "raw_rows": raw_rows,
        "mapping": mapping,
        "mapping_meta": mapping_meta,
    }


def get_draft_rows(service_id: int = 0) -> list[list[str]]:
    """다른 라우트(schedule)에서 가장 최근 업로드/붙여넣기 결과에 접근하기 위한 헬퍼."""
    return _draft_rows_by_service.get(service_id, [])
