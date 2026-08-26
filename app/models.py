"""
데이터 모델 정의 (dataclass).

BillingRow   — 청구 대상 행 (호실번호, 세입자명, 연락처, 금액 및 유효성)
SendResult   — messageId, groupId, to, statusCode, statusMessage, dateProcessed
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BillingRow:
    phone: str
    unit: str = ""
    valid: bool = True
    errors: "list[str]" = field(default_factory=list)
    data: "dict" = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phone": self.phone,
            "unit": self.unit,
            "valid": self.valid,
            "errors": self.errors,
            "data": self.data,
        }


@dataclass
class SendResult:
    message_id: Optional[str]
    group_id: Optional[str]
    to: str
    status_code: Optional[str] = None
    status_message: Optional[str] = None
    date_processed: Optional[str] = None

