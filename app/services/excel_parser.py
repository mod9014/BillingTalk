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

# 헤더 텍스트(공백 제거, 대소문자 무시) -> 표준 필드명.
# 엑셀/붙여넣기 모두 이 별칭 목록으로 컬럼을 찾는다. 순서는 상관없다.
COLUMN_ALIASES: dict[str, list[str]] = {
    "unit": ["호실", "호수", "호실번호"],
    "tenant_name": ["입주자명", "성명", "이름", "임차인", "임차인명"],
    "phone": ["연락처", "전화번호", "휴대폰", "휴대폰번호", "핸드폰", "핸드폰번호"],
    "rent": ["임대료", "월세"],
    "general_fee": ["일반관리비", "관리비"],
    "parking_fee": ["주차료"],
    "etc_fee": ["기타", "기타금액"],
    "electricity_fee": ["전기료", "전기세"],
    "water_fee": ["수도료", "수도세"],
    "tv_fee": ["tv수신료", "티비수신료"],
    "prev_unpaid": ["전월미납금", "미납금", "전월미납"],
    "amount_on_time": ["납기내금액", "납기내 금액", "청구금액", "합계"],
    "amount_late": ["납기후금액", "납기후 금액"],
    "due_date": ["납부기한", "납기일"],
}

REQUIRED_FIELDS = ["unit", "tenant_name", "phone"]


def _normalize_header(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _build_header_lookup() -> dict[str, str]:
    lookup = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lookup[_normalize_header(alias)] = field_name
    return lookup


_HEADER_LOOKUP = _build_header_lookup()


def _map_headers(header_row: list) -> dict[int, str]:
    """열 인덱스 -> 표준 필드명. 알 수 없는 헤더는 매핑에서 제외."""
    col_map = {}
    for idx, cell in enumerate(header_row):
        normalized = _normalize_header(cell)
        if normalized in _HEADER_LOOKUP:
            col_map[idx] = _HEADER_LOOKUP[normalized]
    return col_map


def _find_header_row(matrix: list[list]) -> tuple[int, dict[int, str]]:
    """데이터의 첫 줄을 무조건 헤더로 보지 않고, 헤더 별칭과 가장 잘 매칭되는 행을
    상단 몇 줄 안에서 찾는다. (제목 행이 섞여 있거나, 헤더가 둘째 줄에 있는 경우 대비)"""
    search_range = matrix[: min(len(matrix), 10)]

    best_idx = 0
    best_map: dict[int, str] = {}
    best_score = -1

    for idx, row in enumerate(search_range):
        col_map = _map_headers(row)
        required_hit = sum(1 for f in REQUIRED_FIELDS if f in col_map.values())
        score = required_hit * 10 + len(col_map)
        if score > best_score:
            best_score = score
            best_idx = idx
            best_map = col_map

    return best_idx, best_map


def parse_excel(file_bytes: bytes) -> list[list[str]]:
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet = workbook.active
    matrix = [list(str(cell or "") for cell in row) for row in sheet.iter_rows(values_only=True)]

    header_idx, _ = _find_header_row(matrix)

    rows = matrix[header_idx:]

    if not rows:
        raise ValueError("데이터가 없습니다.")

    return rows


def parse_pasted_text(text: str) -> list[list[str]]:
    if not text or not text.strip():
        raise ValueError("붙여넣은 내용이 없습니다.")

    lines = [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip() != ""]
    matrix = [line.split("\t") for line in lines]

    header_idx, _ = _find_header_row(matrix)

    rows = matrix[header_idx:]

    if not rows:
        raise ValueError("데이터가 없습니다.")

    return rows



def map_to_template_vars(row: BillingRow, config: dict, year: int, month: int) -> dict[str, str]:
    """BillingRow -> ailmtalk.template의 #{변수명} 딕셔너리 (Solapi kakaoOptions.variables 형식)."""

    def money(n: int) -> str:
        return f"{n:,}"

    return {
        "#{청구년}": str(year),
        "#{청구월}": str(month),
        "#{오피스텔명}": config.get("building_name", ""),
        "#{호실}": row.unit,
        "#{입주자명}": row.tenant_name,
        "#{임대료}": money(row.rent),
        "#{일반관리비}": money(row.general_fee),
        "#{주차료}": money(row.parking_fee),
        "#{기타}": money(row.etc_fee),
        "#{전기료}": money(row.electricity_fee),
        "#{수도료}": money(row.water_fee),
        "#{TV수신료}": money(row.tv_fee),
        "#{전월미납금}": money(row.prev_unpaid),
        "#{납기내금액}": money(row.amount_on_time),
        "#{납기후금액}": money(row.amount_late),
        "#{총금액}": money(row.amount_on_time),
        "#{납부기한}": row.due_date,
        "#{관리소연락처}": config.get("office_phone", ""),
    }
