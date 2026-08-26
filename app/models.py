"""
데이터 모델 정의 (dataclass).

BillingRow   — 청구 대상 행 (호실번호, 세입자명, 연락처, 금액 및 유효성)
SendResult   — messageId, groupId, to, statusCode, statusMessage, dateProcessed
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BillingRow:
    unit: str
    tenant_name: str
    phone: str
    rent: int = 0                 # 임대료
    general_fee: int = 0          # 일반관리비
    parking_fee: int = 0          # 주차료
    etc_fee: int = 0              # 기타
    electricity_fee: int = 0      # 전기료
    water_fee: int = 0            # 수도료
    tv_fee: int = 0                # TV수신료
    prev_unpaid: int = 0          # 전월미납금
    amount_on_time: int = 0       # 납기내금액
    amount_late: int = 0          # 납기후금액 (연체료 2% 적용)
    due_date: str = ""            # 납부기한
    valid: bool = True
    errors: "list[str]" = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "unit": self.unit,
            "tenant_name": self.tenant_name,
            "phone": self.phone,
            "rent": self.rent,
            "general_fee": self.general_fee,
            "parking_fee": self.parking_fee,
            "etc_fee": self.etc_fee,
            "electricity_fee": self.electricity_fee,
            "water_fee": self.water_fee,
            "tv_fee": self.tv_fee,
            "prev_unpaid": self.prev_unpaid,
            "amount_on_time": self.amount_on_time,
            "amount_late": self.amount_late,
            "due_date": self.due_date,
            "valid": self.valid,
            "errors": self.errors,
        }


@dataclass
class SendResult:
    message_id: Optional[str]
    group_id: Optional[str]
    to: str
    status_code: Optional[str] = None
    status_message: Optional[str] = None
    date_processed: Optional[str] = None

