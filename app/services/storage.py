"""
로컬 SQLite 저장소. 개인정보(세입자명/연락처)가 실제로 눕는 유일한 파일.
~/.officetel-bill/data.db 에 저장되며 저장소(git)에는 포함되지 않는다.

init_db()             — 테이블 생성 (services, billing, send_log, excel_headers, template_mapping)
save_send_batch(...)  — 예약 발송 등록 직후, 대상 행 + Solapi 응답을 함께 기록
update_send_status()  — 상태 폴링 결과 반영
get_summary()         — 전체/완료/대기/실패 건수 + 상세 목록 (대시보드용, 주기별 필터링 지원)
check_duplicates(...) — 동일 주기 내 중복 발송 여부 검사
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.models import BillingRow, SendResult

DB_DIR = Path.home() / ".officetel-bill"
DB_PATH = DB_DIR / "data.db"
SECRET_KEY_PATH = DB_DIR / "secret.key"

# DB에 암호화하여 저장할 민감 필드 목록
_ENCRYPTED_FIELDS = {"solapi_secret"}


VALID_SEND_CYCLES = {"daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly"}



def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 암호화 헬퍼
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """Fernet 인스턴스를 반환. 키 파일이 없으면 새로 생성."""
    DB_DIR.mkdir(exist_ok=True)
    if not SECRET_KEY_PATH.exists():
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
        SECRET_KEY_PATH.chmod(0o600)  # 소유자 읽기/쓰기 전용
    else:
        key = SECRET_KEY_PATH.read_bytes()
    return Fernet(key)


def _encrypt(value: str) -> str:
    """문자열을 암호화하여 'enc:' 접두사를 붙인 Base64 문자열로 반환."""
    token = _get_fernet().encrypt(value.encode())
    return "enc:" + token.decode()


def _decrypt(value: str) -> str:
    """'enc:' 접두사가 있는 암호화 문자열을 복호화. 평문이면 그대로 반환(레거시 호환)."""
    if not value.startswith("enc:"):
        return value  # 기존 평문값 그대로 반환
    try:
        return _get_fernet().decrypt(value[4:].encode()).decode()
    except (InvalidToken, Exception):
        return value  # 복호화 실패 시 원본 반환


@contextmanager
def _connect():
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        # 서비스 테이블 (발송 주기 send_cycle, 발신 프로필 pf_id, 선택 템플릿 ID template_id, 템플릿 정보 및 수정일시 포함)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                send_cycle TEXT NOT NULL DEFAULT 'monthly',
                pf_id TEXT NOT NULL DEFAULT '',
                template_id TEXT NOT NULL DEFAULT '',
                template_data TEXT DEFAULT '',
                template_date_updated TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS billing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL DEFAULT 0,
                cycle_key TEXT NOT NULL DEFAULT '',
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                unit TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                template_vars TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS send_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                billing_id INTEGER NOT NULL REFERENCES billing(id),
                message_id TEXT,
                group_id TEXT,
                to_phone TEXT NOT NULL,
                status_code TEXT,
                status_label TEXT NOT NULL DEFAULT 'pending',
                status_message TEXT,
                processed_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS excel_headers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL DEFAULT 0,
                header_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS template_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL DEFAULT 0,
                template_var TEXT NOT NULL,
                excel_header TEXT NOT NULL,
                field_type TEXT NOT NULL DEFAULT 'text',
                required INTEGER NOT NULL DEFAULT 1,
                default_value TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        # 템플릿 테이블 (service_id 외래키 연동)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL UNIQUE,
                template_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                variables TEXT NOT NULL DEFAULT '[]',
                buttons TEXT NOT NULL DEFAULT '[]',
                extra TEXT DEFAULT '',
                ad TEXT DEFAULT '',
                emphasize_type TEXT DEFAULT '',
                emphasize_title TEXT DEFAULT '',
                header TEXT DEFAULT '',
                highlight TEXT DEFAULT '{}',
                item TEXT DEFAULT '{}',
                status TEXT DEFAULT '',
                date_created TEXT DEFAULT '',
                date_updated TEXT DEFAULT '',
                raw_data TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
            )
        """)
        # 전역 시스템 설정 테이블 (Solapi 인증키, 대체발송번호 등)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # 기존 테이블에 추가 컬럼 마이그레이션
        _migrate_columns(conn)



def get_app_config() -> dict[str, str]:
    """DB에 저장된 전역 설정 조회 (암호화 필드는 복호화하여 반환)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
        config_dict = {r["key"]: r["value"] for r in rows}

    # 암호화 필드 복호화
    for field in _ENCRYPTED_FIELDS:
        if field in config_dict:
            config_dict[field] = _decrypt(config_dict[field])

    return config_dict


def save_app_config(data: dict) -> dict[str, str]:
    """전역 설정을 DB에 저장(upsert)하고 최신 설정을 반환한다. 빈 문자열인 비밀번호 등은 기존값 유지."""
    init_db()
    current = get_app_config()
    now = _now()

    # 업데이트할 데이터 병합 (기존값 유지 처리)
    merged = dict(current)
    for k, v in data.items():
        if v is None:
            continue
        v_str = str(v).strip()
        # API Secret 등의 경우 비워두면 기존값 유지
        if k in ("solapi_key", "solapi_secret") and v_str == "":
            continue
        merged[k] = v_str

    with _connect() as conn:
        for k, v in merged.items():
            # 암호화 필드는 암호화하여 저장
            store_v = _encrypt(v) if k in _ENCRYPTED_FIELDS and v else v
            conn.execute(
                """INSERT INTO app_config (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (k, store_v, now),
            )

    return merged


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """기존 DB에 누락된 컬럼(service_id, send_cycle, pf_id, template_id, template_data, template_date_updated, cycle_key) 추가 마이그레이션."""
    # services -> send_cycle, pf_id, template_id, template_data, template_date_updated
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(services)").fetchall()]
        if "send_cycle" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN send_cycle TEXT NOT NULL DEFAULT 'monthly'")
        if "pf_id" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN pf_id TEXT NOT NULL DEFAULT ''")
        if "template_id" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN template_id TEXT NOT NULL DEFAULT ''")
        if "template_data" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN template_data TEXT DEFAULT ''")
        if "template_date_updated" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN template_date_updated TEXT DEFAULT ''")
    except Exception:
        pass


    # billing -> service_id, cycle_key
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(billing)").fetchall()]
        if "service_id" not in cols:
            conn.execute("ALTER TABLE billing ADD COLUMN service_id INTEGER NOT NULL DEFAULT 0")
        if "cycle_key" not in cols:
            conn.execute("ALTER TABLE billing ADD COLUMN cycle_key TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    # excel_headers / template_mapping -> service_id
    for table in ["excel_headers", "template_mapping"]:
        try:
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "service_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN service_id INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

    # template_mapping -> field_type, required, default_value
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(template_mapping)").fetchall()]
        if "field_type" not in cols:
            conn.execute("ALTER TABLE template_mapping ADD COLUMN field_type TEXT NOT NULL DEFAULT 'text'")
        if "required" not in cols:
            conn.execute("ALTER TABLE template_mapping ADD COLUMN required INTEGER NOT NULL DEFAULT 1")
        if "default_value" not in cols:
            conn.execute("ALTER TABLE template_mapping ADD COLUMN default_value TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 발송 주기(Cycle) 계산 유틸
# ---------------------------------------------------------------------------

def compute_cycle_key(date_str: str, cycle: str = "monthly") -> tuple[str, str]:
    """
    날짜 문자열("YYYY-MM-DD" 등)과 주기(daily, weekly, monthly, quarterly, half_yearly, yearly)에 따라
    고유한 cycle_key 및 사람이 읽기 편한 cycle_label을 반환한다.
    """
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        dt = datetime.now()

    year = dt.year
    month = dt.month
    day = dt.day

    c = cycle.lower() if cycle else "monthly"

    if c == "daily":
        key = dt.strftime("%Y-%m-%d")
        label = f"{year}년 {month:02d}월 {day:02d}일"
    elif c == "weekly":
        iso_year, iso_week, _ = dt.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        label = f"{iso_year}년 {iso_week}주차"
    elif c == "quarterly":
        quarter = (month - 1) // 3 + 1
        key = f"{year}-Q{quarter}"
        label = f"{year}년 {quarter}분기"
    elif c == "half_yearly":
        half = 1 if month <= 6 else 2
        half_name = "상반기" if half == 1 else "하반기"
        key = f"{year}-H{half}"
        label = f"{year}년 {half_name}"
    elif c == "yearly":
        key = f"{year}"
        label = f"{year}년"
    else:  # monthly (기본값)
        key = f"{year}-{month:02d}"
        label = f"{year}년 {month:02d}월"

    return key, label


# ---------------------------------------------------------------------------
# 서비스 CRUD
# ---------------------------------------------------------------------------

def create_service(
    name: str,
    description: str = "",
    send_cycle: str = "monthly",
    pf_id: str = "",
    template_id: str = "",
):
    """새 서비스를 생성하고 ID를 반환한다."""
    init_db()
    now = _now()
    cycle = send_cycle if send_cycle in VALID_SEND_CYCLES else "monthly"
    t_id = template_id or ""
    p_id = pf_id or ""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO services 
            (name, description, send_cycle, pf_id, template_id, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, description, cycle, p_id, t_id, now, now),
        )
        return cur.lastrowid


def update_service(
    service_id: int,
    name: str,
    description: str = "",
    send_cycle: str = "monthly",
    pf_id: str = "",
    template_id: str = "",
) -> None:
    """서비스 이름/설명/발송주기/pfId/템플릿ID를 수정한다."""
    init_db()
    cycle = send_cycle if send_cycle in VALID_SEND_CYCLES else "monthly"
    t_id = template_id or ""
    p_id = pf_id or ""

    with _connect() as conn:
        conn.execute(
            """UPDATE services 
            SET name = ?, description = ?, send_cycle = ?, pf_id = ?, template_id = ?, updated_at = ? 
            WHERE id = ?""",
            (name, description, cycle, p_id, t_id, _now(), service_id),
        )


def list_services() -> list[dict]:
    """등록된 모든 서비스 목록을 반환한다."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, description, send_cycle, pf_id, template_id, created_at, updated_at FROM services ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_service(service_id: int) -> dict | None:
    """특정 서비스 정보를 반환한다."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, send_cycle, pf_id, template_id, created_at, updated_at FROM services WHERE id = ?",
            (service_id,),
        ).fetchone()
        return dict(row) if row else None


def save_service_template(service_id: int, template_data: dict) -> None:
    """외래키(service_id)로 연결된 templates 테이블에 템플릿 정보를 저장(UPSERT)한다."""
    init_db()
    if not service_id or not template_data:
        return

    now = _now()
    tid = str(template_data.get("templateId") or template_data.get("id") or "").strip()
    name = str(template_data.get("name") or template_data.get("title") or tid).strip()
    content = template_data.get("content") or ""

    # 변수 목록
    raw_vars = template_data.get("variables") or []
    var_names = []
    if isinstance(raw_vars, list):
        for v in raw_vars:
            if isinstance(v, dict) and v.get("name"):
                var_names.append(str(v["name"]).strip())
            elif isinstance(v, str):
                var_names.append(v.strip())

    buttons = template_data.get("buttons") or []
    extra = template_data.get("extra") or ""
    ad = template_data.get("ad") or ""
    emphasize_type = template_data.get("emphasizeType") or template_data.get("emphasize_type") or ""
    emphasize_title = template_data.get("emphasizeTitle") or template_data.get("emphasize_title") or ""
    header = template_data.get("header") or ""
    highlight = template_data.get("highlight") or {}
    item = template_data.get("item") or {}
    status = template_data.get("status") or ""
    date_created = template_data.get("dateCreated") or template_data.get("date_created") or ""
    date_updated = template_data.get("dateUpdated") or template_data.get("date_updated") or ""

    with _connect() as conn:
        conn.execute(
            """INSERT INTO templates (
                service_id, template_id, name, content, variables, buttons,
                extra, ad, emphasize_type, emphasize_title, header, highlight,
                item, status, date_created, date_updated, raw_data, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id) DO UPDATE SET
                template_id = excluded.template_id,
                name = excluded.name,
                content = excluded.content,
                variables = excluded.variables,
                buttons = excluded.buttons,
                extra = excluded.extra,
                ad = excluded.ad,
                emphasize_type = excluded.emphasize_type,
                emphasize_title = excluded.emphasize_title,
                header = excluded.header,
                highlight = excluded.highlight,
                item = excluded.item,
                status = excluded.status,
                date_created = excluded.date_created,
                date_updated = excluded.date_updated,
                raw_data = excluded.raw_data,
                updated_at = excluded.updated_at
            """,
            (
                service_id,
                tid,
                name,
                content,
                json.dumps(var_names, ensure_ascii=False),
                json.dumps(buttons, ensure_ascii=False),
                extra,
                ad,
                emphasize_type,
                emphasize_title,
                header,
                json.dumps(highlight, ensure_ascii=False) if isinstance(highlight, dict) else str(highlight),
                json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item),
                status,
                date_created,
                date_updated,
                json.dumps(template_data, ensure_ascii=False),
                now,
                now,
            ),
        )


def get_service_template(service_id: int) -> dict | None:
    """외래키(service_id)로 저장된 템플릿 정보를 조회한다."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE service_id = ?",
            (service_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["variables"] = json.loads(d.get("variables") or "[]")
        except Exception:
            d["variables"] = []
        try:
            d["buttons"] = json.loads(d.get("buttons") or "[]")
        except Exception:
            d["buttons"] = []
        try:
            d["highlight"] = json.loads(d.get("highlight") or "{}")
        except Exception:
            d["highlight"] = {}
        try:
            d["item"] = json.loads(d.get("item") or "{}")
        except Exception:
            d["item"] = {}
        return d


def delete_service(service_id: int) -> None:
    """서비스 및 연결된 템플릿/헤더/매핑/billing/send_log를 모두 삭제한다."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM send_log WHERE billing_id IN (SELECT id FROM billing WHERE service_id = ?)",
            (service_id,),
        )
        conn.execute("DELETE FROM billing WHERE service_id = ?", (service_id,))
        conn.execute("DELETE FROM excel_headers WHERE service_id = ?", (service_id,))
        conn.execute("DELETE FROM template_mapping WHERE service_id = ?", (service_id,))
        conn.execute("DELETE FROM templates WHERE service_id = ?", (service_id,))
        conn.execute("DELETE FROM services WHERE id = ?", (service_id,))



# ---------------------------------------------------------------------------
# 엑셀 헤더 (서비스별)
# ---------------------------------------------------------------------------

def save_excel_headers(headers: list[str], service_id: int = 0) -> None:
    """엑셀 헤더 컬럼 목록을 각각의 행(row)으로 DB에 저장."""
    init_db()
    now = _now()
    with _connect() as conn:
        conn.execute("DELETE FROM excel_headers WHERE service_id = ?", (service_id,))
        for idx, h in enumerate(headers):
            h_str = str(h).strip()
            if h_str:
                conn.execute(
                    "INSERT INTO excel_headers (service_id, header_name, sort_order, created_at) VALUES (?, ?, ?, ?)",
                    (service_id, h_str, idx, now),
                )


def get_excel_headers(service_id: int = 0) -> list[str]:
    """DB에 저장된 엑셀 헤더 컬럼 목록 조회 (정렬 순서 기준)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT header_name FROM excel_headers WHERE service_id = ? ORDER BY sort_order ASC, id ASC",
            (service_id,),
        ).fetchall()
        return [r["header_name"] for r in rows]


# ---------------------------------------------------------------------------
# 템플릿 매핑 (서비스별)
# ---------------------------------------------------------------------------

def save_template_mapping(
    mapping: dict[str, str],
    service_id: int = 0,
    mapping_meta: dict | None = None,
) -> None:
    """템플릿 변수 ↔ 엑셀 헤더 매핑(+유형/필수/기본값)을 각각의 행(row)으로 DB에 저장."""
    init_db()
    now = _now()
    meta = mapping_meta or {}
    with _connect() as conn:
        conn.execute("DELETE FROM template_mapping WHERE service_id = ?", (service_id,))
        for tvar, ehead in mapping.items():
            tvar_str = str(tvar).strip()
            if tvar_str:
                var_meta = meta.get(tvar_str, {})
                conn.execute(
                    """INSERT INTO template_mapping
                         (service_id, template_var, excel_header, field_type, required, default_value, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        service_id,
                        tvar_str,
                        str(ehead).strip() if ehead else "",
                        str(var_meta.get("type", "text")),
                        1 if var_meta.get("required", True) else 0,
                        str(var_meta.get("defaultValue", "")),
                        now,
                    ),
                )


def get_template_mapping(service_id: int = 0) -> dict[str, str]:
    """DB에 저장된 템플릿 변수 매핑 목록 조회 (excel_header 값만 반환)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT template_var, excel_header FROM template_mapping WHERE service_id = ? ORDER BY id ASC",
            (service_id,),
        ).fetchall()
        return {r["template_var"]: r["excel_header"] for r in rows}


def get_mapping_meta(service_id: int = 0) -> dict[str, dict]:
    """DB에 저장된 변수별 메타(유형/필수/기본값) 조회."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT template_var, field_type, required, default_value FROM template_mapping WHERE service_id = ? ORDER BY id ASC",
            (service_id,),
        ).fetchall()
        return {
            r["template_var"]: {
                "type": r["field_type"] or "text",
                "required": bool(r["required"]),
                "defaultValue": r["default_value"] or "",
            }
            for r in rows
        }


# ---------------------------------------------------------------------------
# 중복 발송 검사
# ---------------------------------------------------------------------------

def check_duplicates(
    service_id: int,
    scheduled_date: str,
    target_units: list[str],
    explicit_cycle_key: str | None = None,
) -> dict:
    """
    동일 서비스의 발송 주기 내에 이미 발송/예약된 내역이 있는지 검사한다.
    explicit_cycle_key가 주어지면 해당 키를 우선 사용한다.
    """
    init_db()
    svc = get_service(service_id)
    send_cycle = svc["send_cycle"] if svc else "monthly"
    if explicit_cycle_key:
        cycle_key = explicit_cycle_key
        # label 생성을 위해 날짜 파싱 시도
        _, cycle_label = compute_cycle_key(scheduled_date, send_cycle)
    else:
        cycle_key, cycle_label = compute_cycle_key(scheduled_date, send_cycle)

    with _connect() as conn:
        # 해당 주기에 이미 등록된 billing 행 목록
        rows = conn.execute(
            """SELECT b.unit, b.phone, b.tenant_name, s.status_label
               FROM billing b
               LEFT JOIN send_log s ON s.billing_id = b.id
               WHERE b.service_id = ? AND b.cycle_key = ?""",
            (service_id, cycle_key),
        ).fetchall()

        existing_units = {r["unit"] for r in rows if r["unit"]}
        matched_units = [u for u in target_units if u in existing_units]

        return {
            "has_duplicates": len(matched_units) > 0,
            "cycle_key": cycle_key,
            "cycle_label": cycle_label,
            "send_cycle": send_cycle,
            "duplicate_units": matched_units,
            "duplicate_count": len(matched_units),
            "existing_total": len(rows),
        }


# ---------------------------------------------------------------------------
# 발송 배치 저장 (서비스별 & 주기별)
# ---------------------------------------------------------------------------

def save_send_batch(
    rows: list[BillingRow],
    template_vars_list: list[dict],
    results: list[SendResult],
    year: int,
    month: int,
    service_id: int = 0,
    cycle_key: str = "",
) -> None:
    """예약 발송 등록 직후 호출. rows[i] <-> template_vars_list[i] <-> results[i] 인덱스가 대응된다."""
    init_db()
    if not cycle_key:
        svc = get_service(service_id)
        send_cycle = svc["send_cycle"] if svc else "monthly"
        # 기본 날짜로 cycle_key 산출
        date_str = f"{year}-{month:02d}-01"
        cycle_key, _ = compute_cycle_key(date_str, send_cycle)

    with _connect() as conn:
        for row in rows:
            result = next(result for result in results if result.to == row.unit)
            cur = conn.execute(
                """INSERT INTO billing
                   (service_id, cycle_key, year, month, unit, tenant_name, phone, template_vars, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (service_id, cycle_key, year, month, row.unit, row.tenant_name, row.phone,
                 "", _now()),
            )
            billing_id = cur.lastrowid
            conn.execute(
                """INSERT INTO send_log
                   (billing_id, message_id, group_id, to_phone, status_code, status_label, status_message, processed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (billing_id, result.message_id, result.group_id, row.phone,
                 result.status_code, result.status_message, result.status_message,
                 result.date_processed, _now()),
            )


def get_pending_group_ids(service_id: int | None = None) -> list[str]:
    """아직 최종 상태(성공/실패)가 아닌 발송 건들의 groupId 목록 (폴링 대상)."""
    init_db()
    with _connect() as conn:
        if service_id is not None:
            rows = conn.execute(
                """SELECT DISTINCT s.group_id FROM send_log s
                   JOIN billing b ON b.id = s.billing_id
                   WHERE s.status_label = 'pending' AND s.group_id IS NOT NULL AND b.service_id = ?""",
                (service_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT group_id FROM send_log WHERE status_label = 'pending' AND group_id IS NOT NULL"
            ).fetchall()
        return [r["group_id"] for r in rows]


def update_send_status(results: list[SendResult]) -> None:
    """폴링(GET /status)으로 받아온 최신 상태를 message_id 기준으로 반영."""
    if not results:
        return
    with _connect() as conn:
        for result in results:
            conn.execute(
                """UPDATE send_log
                   SET status_code = ?, status_label = ?, status_message = ?, processed_at = ?, updated_at = ?
                   WHERE message_id = ?""",
                (result.status_code, result.status, result.status_message,
                 result.date_processed, _now(), result.message_id),
            )


def get_summary(
    year: int | None = None,
    month: int | None = None,
    service_id: int | None = None,
    cycle_key: str | None = None,
) -> dict:
    init_db()
    with _connect() as conn:
        conditions = []
        params: list = []
        if year is not None and month is not None:
            conditions.append("b.year = ? AND b.month = ?")
            params.extend([year, month])
        if service_id is not None:
            conditions.append("b.service_id = ?")
            params.append(service_id)
        if cycle_key:
            conditions.append("b.cycle_key = ?")
            params.append(cycle_key)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = conn.execute(
            f"""SELECT b.unit, b.tenant_name, b.phone, b.cycle_key, s.status_code, s.status_label, s.status_message, s.processed_at
                FROM send_log s JOIN billing b ON b.id = s.billing_id
                {where}
                ORDER BY s.id DESC""",
            tuple(params),
        ).fetchall()

    result_rows = []
    counts = {"success": 0, "pending": 0, "failed": 0}
    for r in rows:
        status = _normalize_status(r["status_code"] or "1")
        counts[status] = counts.get(status, 0) + 1
        result_rows.append({
            "unit": r["unit"],
            "tenantName": r["tenant_name"],
            "phone": r["phone"],
            "cycleKey": r["cycle_key"],
            "status": status,
            "statusLabel": r["status_label"],
            "processedAt": r["processed_at"],
        })

    return {
        "total": len(result_rows),
        "success": counts["success"],
        "pending": counts["pending"],
        "failed": counts["failed"],
        "rows": result_rows,
    }
def _normalize_status(status_code: str) -> str:
    """
    1xxx	접수 중 오류
    2000	정상 접수
    2xxx	플랫폼 내부 처리 중 오류
    3000	이통사로 접수 완료(정상)
    3xxx	통신사에서 처리 중 오류
    4000	발송 처리를 완료함
    """
    status_code_int = int(status_code)
    if status_code_int % 1000 != 0:
        return "failed"
    elif 3000 >= status_code_int:
        return "pending"
    else:
        return "success"