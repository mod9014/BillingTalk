"""
Solapi 카카오 알림톡 v2 템플릿 조회 및 변수(#{...}) 추출 서비스.
"""

from __future__ import annotations

import re
from typing import Any

from app.models import KakaoTemplate
from app.services import solapi_client, storage


def extract_variables(content: str) -> list[str]:
    """텍스트에서 #{변수명} 목록을 순서대로 중복 없이 추출."""
    if not content:
        return []
    raw_vars = re.findall(r"#\{([^}]+)\}", content)
    unique_vars = []
    for var in raw_vars:
        var_clean = var.strip()
        if var_clean and var_clean not in unique_vars:
            unique_vars.append(var_clean)
    return unique_vars


def _parse_solapi_variables(solapi_data: dict, content: str) -> list[str]:
    """Solapi v2 템플릿 응답의 variables 및 본문에서 변수명 목록 추출."""
    vars_list: list[str] = []
    raw_variables = solapi_data.get("variables")
    if isinstance(raw_variables, list):
        for item in raw_variables:
            if isinstance(item, dict) and item.get("name"):
                name = str(item["name"]).strip()
                if name and name not in vars_list:
                    if name.startswith("#{") and name.endswith("}"):
                        vars_list.append(name[2:-1])
                    else:
                        vars_list.append(name)
            elif isinstance(item, str):
                name = item.strip()
                if name and name not in vars_list:
                    if name.startswith("#{") and name.endswith("}"):
                        vars_list.append(name[2:-1])
                    else:
                        vars_list.append(name)
    
    return vars_list


def get_template_by_id(template_id: str, config: dict | None = None) -> dict[str, Any] | None:
    """특정 ID의 Solapi 알림톡 템플릿 정보 조회 및 KakaoTemplate 모델로 정규화."""

    cfg = config or storage.get_app_config()
    st = solapi_client.get_solapi_template(template_id, cfg)
    if st:
        content = st.get("content", "")
        vars_list = _parse_solapi_variables(st, content)
        kt = KakaoTemplate.from_dict({
            **st,
            "variables": vars_list,
        })
        d = kt.to_dict()
        d["raw"] = st
        return d

    return None


def load_template_info(template_id: str | None = None, config: dict | None = None) -> dict[str, Any]:
    """템플릿 정보를 로드하는 헬퍼 함수."""
    if template_id:
        t = get_template_by_id(template_id, config)
        if t:
            return t

    return {
        "id": template_id or "",
        "templateId": template_id or "",
        "name": "",
        "title": "",
        "content": "",
        "variables": [],
        "buttons": [],
    }
