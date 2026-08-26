"""
발송 상태 조회(폴링) 라우트. 프론트엔드가 5분 간격 + 새로고침 버튼으로 호출.

GET /status — 아직 최종 상태가 아닌 건들을 services.solapi_client로 재조회 →
              services.storage에 반영 → 요약 반환.
              서비스별(service_id) 및 주기별(cycle_key) 필터링 지원.
"""

from typing import Optional
from fastapi import APIRouter, Query, Request

from app.services import storage
from app.services.solapi_client import SolapiError, get_status

router = APIRouter()


@router.get("/status")
async def get_send_status(
    request: Request,
    service_id: Optional[int] = Query(None),
    cycle_key: Optional[str] = Query(None),
):
    config = request.app.state.config

    for group_id in storage.get_pending_group_ids(service_id):
        try:
            results = get_status(group_id, config)
            storage.update_send_status(results)
        except SolapiError as e:
            # 폴링 중 하나의 그룹이 실패해도 나머지는 계속 진행하고, 요약 응답은 항상 반환한다.
            print(f"⚠️ 상태 조회 실패 (groupId={group_id}): {e}")

    return storage.get_summary(service_id=service_id, cycle_key=cycle_key)
