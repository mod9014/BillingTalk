"""
알림톡 템플릿 목록 조회 및 변수(#{...}) 추출 서비스.
현재는 로컬 파일(*.template)을 읽어 리스트로 제공하며, 향후 외부 API(Solapi 등) 연동을 위해 인터페이스화 됨.
"""

from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TEMPLATE_PATH = ROOT_DIR / "ailmtalk.template"


def extract_variables(content: str) -> list[str]:
    """텍스트에서 #{변수명} 목록을 순서대로 중복 없이 추출."""
    raw_vars = re.findall(r"#\{([^}]+)\}", content)
    unique_vars = []
    for var in raw_vars:
        var_clean = var.strip()
        if var_clean and var_clean not in unique_vars:
            unique_vars.append(var_clean)
    return unique_vars


def list_templates() -> list[dict]:
    """
    사용 가능한 알림톡 템플릿 목록 반환.
    (로컬 디렉토리의 *.template 파일들을 스캔하여 반환)
    """
    templates = []

    # 1. 기본 템플릿 (ailmtalk.template)
    if DEFAULT_TEMPLATE_PATH.exists():
        try:
            with open(DEFAULT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            templates.append({
                "id": "local_default",
                "name": "기본 관리비 청구서 (ailmtalk.template)",
                "source": "local",
                "content": content,
                "variables": extract_variables(content),
            })
        except Exception as e:
            print(f"기본 템플릿 로드 실패: {e}")

    # 2. 기타 로컬 .template 파일들 스캔
    for p in ROOT_DIR.glob("*.template"):
        if p.name != "ailmtalk.template":
            try:
                with open(p, "r", encoding="utf-8") as f:
                    c = f.read()
                templates.append({
                    "id": f"local_{p.stem}",
                    "name": f"{p.stem} ({p.name})",
                    "source": "local",
                    "content": c,
                    "variables": extract_variables(c),
                })
            except Exception:
                pass

    if not templates:
        # fallback
        templates.append({
            "id": "local_default",
            "name": "기본 템플릿 (비어있음)",
            "source": "local",
            "content": "",
            "variables": [],
        })

    return templates


def get_template_by_id(template_id: str) -> dict | None:
    """특정 ID의 템플릿 정보 반환."""
    templates = list_templates()
    for t in templates:
        if t["id"] == template_id:
            return t
    return templates[0] if templates else None


def load_template_info(template_id: str | None = None) -> dict:
    """하위 호환용 헬퍼."""
    if template_id:
        t = get_template_by_id(template_id)
        if t:
            return t
    templates = list_templates()
    return templates[0] if templates else {"content": "", "variables": []}
