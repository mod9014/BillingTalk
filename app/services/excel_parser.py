"""
엑셀 파싱 및 (엑셀 셀 복사→붙여넣기) 텍스트 파싱, 템플릿 변수 매핑.

parse_excel(file_bytes)        — 업로드된 .xlsx 파일 -> 행 데이터 2차원 리스트
parse_pasted_text(text)        — 엑셀에서 복사한 셀 범위를 그대로 붙여넣은 문자열(TSV) -> 행 데이터 2차원 리스트
map_to_template_vars           — BillingRow -> ailmtalk.template의 #{...} 변수 딕셔너리
"""

from __future__ import annotations

import io
import re

import openpyxl

from app.models import BillingRow
from app.services import storage


def _normalize_header(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _find_header_row(matrix: list[list], expected_headers: list[str] | None = None) -> int:
    """
    DB에 저장된 excel_headers 목록과 가장 많이 일치하는 행을 상위 15개 행 안에서 찾는다.
    일치하는 헤더가 없거나 expected_headers가 비어있으면, 유효한 텍스트가 2개 이상 있는 첫 행을 반환.
    """
    if not matrix:
        return 0

    search_range = matrix[: min(len(matrix), 15)]

    # 1. DB의 excel_headers 기반 매칭 탐색
    if expected_headers:
        expected_set = {_normalize_header(h) for h in expected_headers if str(h).strip()}
        if expected_set:
            best_idx = 0
            best_score = 0
            for idx, row in enumerate(search_range):
                row_normalized = {_normalize_header(cell) for cell in row if str(cell).strip()}
                score = len(row_normalized & expected_set)
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_score > 0:
                return best_idx

    # 2. Fallback: 유효 텍스트 셀이 2개 이상 있는 첫 번째 행을 헤더로 간주
    for idx, row in enumerate(search_range):
        non_empty = [str(c).strip() for c in row if str(c).strip() != ""]
        if len(non_empty) >= 2:
            return idx

    return 0


def parse_excel(file_bytes: bytes, service_id: int = 0, expected_headers: list[str] | None = None) -> list[list[str]]:
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    matrix = [list(str(cell or "") for cell in row) for row in sheet.iter_rows(values_only=True)]

    if not matrix:
        raise ValueError("데이터가 없습니다.")

    if expected_headers is None and service_id:
        expected_headers = storage.get_excel_headers(service_id)

    header_idx = _find_header_row(matrix, expected_headers)
    rows = matrix[header_idx:]

    if not rows:
        raise ValueError("데이터가 없습니다.")

    return rows


def parse_pasted_text(text: str, service_id: int = 0, expected_headers: list[str] | None = None) -> list[list[str]]:
    if not text or not text.strip():
        raise ValueError("붙여넣은 내용이 없습니다.")

    lines = [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip() != ""]
    matrix = [line.split("\t") for line in lines]

    if not matrix:
        raise ValueError("데이터가 없습니다.")

    if expected_headers is None and service_id:
        expected_headers = storage.get_excel_headers(service_id)

    header_idx = _find_header_row(matrix, expected_headers)
    rows = matrix[header_idx:]

    if not rows:
        raise ValueError("데이터가 없습니다.")

    return rows


def evaluate_row_template_vars(
    row_dict: dict[str, str],
    mapping: dict[str, str],
    mapping_meta: dict[str, dict],
    config: dict,
    year: int,
    month: int,
    template_vars: list[str] | None = None,
) -> dict[str, str]:
    """
    행 데이터와 서비스 매핑/메타 설정을 바탕으로 알림톡 템플릿 변수(#{변수명}) 딕셔너리를 동적으로 생성.
    어떤 특정 템플릿 변수명도 하드코딩하지 않는다.
    """
    from app.services import formula_evaluator

    result: dict[str, str] = {}
    system_fixed_keys = {"phone", "send_date", "send_time"}

    # 대상 변수 목록 결정
    target_keys = set(template_vars) if template_vars else set(mapping.keys())
    # 시스템 제어 키 제외
    eval_keys = [k for k in target_keys if k not in system_fixed_keys]

    for var_name in eval_keys:
        expr = mapping.get(var_name, f"{{{var_name}}}")
        meta = mapping_meta.get(var_name, {})
        field_type = meta.get("type", "text")

        val = formula_evaluator.evaluate_expression(
            expr=expr,
            row_dict=row_dict,
            config=config,
            year=year,
            month=month,
            field_type=field_type,
        )
        result[f"#{{{var_name}}}"] = val

    return result
