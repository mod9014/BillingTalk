"""
템플릿 매핑 수식 및 수동 입력 평가 모듈 (Formula Evaluator).

지원 기능:
1. 헤더 참조 치환: {호실}, {연락처}, {납부기한} 등
2. 날짜 연산: {납부기한} - 5, {발송일} - 3, {납부기한} + 1
   - '2026-08-25' - 5 => '2026-08-20'
   - '25' (일자) - 5 => 2026년 8월 기준 '2026-08-20'
3. 숫자 사칙연산: {임대료} + {일반관리비}, {납기내금액} * 1.02
4. 시스템/설정 변수: __system_year__, __system_month__,__system_day__
5. 일반 고정 텍스트
6. 유형별 포맷: amount -> 콤마+내림, name -> 마스킹
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional


def _clean_number(val: Any) -> float:
    """통화 기호, 쉼표, 원 등을 제거하고 숫자로 변환."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s = re.sub(r"[^\d.-]", "", s)
    try:
        return float(s) if s not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def format_amount(val: Any) -> str:
    """금액 포맷: 소수점 내림(floor) 후 천 단위 콤마. 빈 값이면 그대로 반환."""
    s = str(val).strip()
    if not s:
        return s
    num = _clean_number(s)
    if num == 0.0 and s not in ("0", "0.0", "0원"):
        # 숫자가 아닌 텍스트면 그대로 반환
        if not re.match(r"^-?[\d,.]+", s):
            return s
    floored = math.floor(num)
    return f"{floored:,}"


def mask_name(name: str) -> str:
    """
    한국식 이름 마스킹:
    - 2글자: 홍* (첫글자만 노출)
    - 3글자: 홍*동 (가운데 마스킹)
    - 4글자 이상: 홍**동 (가운데 전부 마스킹)
    - 영문/숫자 등 기타: 첫글자 + ** 처리
    """
    name = str(name).strip()
    if not name:
        return name
    n = len(name)
    if n == 1:
        return name
    if n == 2:
        return name[0] + "*"
    if n == 3:
        return name[0] + "*" + name[2]
    # 4글자 이상: 첫글자 + 가운데 전부 * + 마지막 글자
    return name[0] + "*" * (n - 2) + name[-1]


def _parse_date(val: Any, year: int, month: int) -> Optional[date]:
    """다양한 형식의 날짜 문자열/숫자를 date 객체로 파싱."""
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()

    s = str(val).strip()
    # 1) YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
    m_full = re.match(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m_full:
        try:
            return date(int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3)))
        except ValueError:
            pass

    # 2) MM-DD, MM/DD
    m_short = re.match(r"^(\d{1,2})[-./](\d{1,2})$", s)
    if m_short:
        try:
            return date(year, int(m_short.group(1)), int(m_short.group(2)))
        except ValueError:
            pass

    # 3) '25일', '25' 등 일자만 있는 경우
    m_day = re.match(r"^(\d{1,2})\s*일?$", s)
    if m_day:
        day_num = int(m_day.group(1))
        try:
            return date(year, month, day_num)
        except ValueError:
            pass

    return None


def evaluate_expression(
    expr: str,
    row_dict: dict[str, Any],
    config: Optional[dict] = None,
    year: int = 0,
    month: int = 0,
    is_date_field: bool = False,
    field_type: str = "text",  # 'text' | 'name' | 'phone' | 'date' | 'amount'
) -> str:
    """
    expr: 매핑 수식 (예: '{납부기한} - 5', '{호실}', '{임대료} + {관리비}', '__system_year__')
    row_dict: 행 데이터 {헤더명: 셀값}
    field_type: 유형에 따라 최종값 포맷 적용
      - 'amount' : 내림(floor) + 천 단위 콤마  예) 150000 -> '150,000'
      - 'name'   : 한국식 이름 마스킹          예) '홍길동' -> '홍*동'
      - 기타     : 그대로 반환
    """
    if not expr:
        return ""

    expr = str(expr).strip()
    config = config or {}
    now = datetime.now()
    if year == 0:
        year = now.year
    if month == 0:
        month = now.month

    # is_date_field 호환: field_type이 date면 동일하게 동작
    if field_type == "date":
        is_date_field = True

    evaluated: Optional[str] = None

    # 시스템/설정 고정값 처리
    if expr == "__system_year__":
        evaluated = str(year)
    elif expr == "__system_month__":
        evaluated = str(month)
    elif expr in row_dict:
        # 단일 헤더명 (괄호 없이 헤더명 그대로 들어온 경우 호환)
        val = row_dict[expr]
        evaluated = "" if val is None else str(val)

    # 1. 날짜 연산 확인: {헤더} +/- N (예: {납부기한} - 5, {발송일} - 3)
    if evaluated is None:
        date_math_match = re.match(r"^\{([^}]+)\}\s*([+-])\s*(\d+)\s*(?:일|days?)?$", expr, re.IGNORECASE)
        if date_math_match:
            header_name = date_math_match.group(1).strip()
            op = date_math_match.group(2)
            days_delta = int(date_math_match.group(3))
            raw_val = row_dict.get(header_name, "")
            base_date = _parse_date(raw_val, year, month)
            if base_date:
                delta = timedelta(days=days_delta if op == "+" else -days_delta)
                res_date = base_date + delta
                evaluated = res_date.strftime("%Y-%m-%d")

    # 2. 산술 연산 확인: {A} + {B}, {A} * 1.02 등
    if evaluated is None and re.search(r"\{[^}]+\}", expr) and any(op in expr for op in ("+", "-", "*", "/")):
        def _sub_num(match):
            h = match.group(1).strip()
            val = row_dict.get(h, 0)
            return str(_clean_number(val))

        try:
            num_expr = re.sub(r"\{([^}]+)\}", _sub_num, expr)
            # 산술식 안전성 검증 (숫자, 공백, 사칙연산, 소수점, 괄호만 허용)
            if re.match(r"^[\d\s+\-*/.()]+$", num_expr):
                # 안전한 계산 (eval 제한)
                res_num = eval(num_expr, {"__builtins__": None}, {})
                if isinstance(res_num, (int, float)):
                    evaluated = f"{int(res_num)}" if float(res_num).is_integer() else f"{res_num:.2f}"
        except Exception:
            pass

    # 3. 텍스트 치환 ({헤더명} -> 셀값)
    if evaluated is None:
        def _sub_text(match):
            h = match.group(1).strip()
            if h == "__system_year__":
                return str(year)
            if h == "__system_month__":
                return str(month)
            if h == "__system_day__":
                return str(now.day)
            val = row_dict.get(h, "")
            return "" if val is None else str(val)

        evaluated = re.sub(r"\{([^}]+)\}", _sub_text, expr)

    # 날짜 필드인 경우 정규화 (YYYY-MM-DD)
    if is_date_field and evaluated:
        parsed_dt = _parse_date(evaluated, year, month)
        if parsed_dt:
            evaluated = parsed_dt.strftime("%Y-%m-%d")

    # ── 유형별 최종 포맷 후처리 ──────────────────────────────────────────────
    if evaluated and field_type == "amount":
        evaluated = format_amount(evaluated)
    elif evaluated and field_type == "name":
        evaluated = mask_name(evaluated)

    return evaluated
