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
    tenant_name: str = ""
    valid: bool = True
    errors: "list[str]" = field(default_factory=list)
    data: "dict" = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phone": self.phone,
            "unit": self.unit,
            "tenant_name": self.tenant_name,
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
    status: Optional[str] = None
    status_message: Optional[str] = None
    date_processed: Optional[str] = None


@dataclass
class TemplateButton:
    """알림톡 버튼 정의 (WL: 웹링크, AL: 앱링크, DS: 배송조회, BK: 봇키워드, MD: 메시지전달, CA: 채널추가, BC: 상담톡)."""
    button_type: str = "WL"
    button_name: str = ""
    link_mo: Optional[str] = None
    link_pc: Optional[str] = None
    link_and: Optional[str] = None
    link_ios: Optional[str] = None
    chat_extra: Optional[str] = None
    target_out: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateButton":
        return cls(
            button_type=data.get("buttonType") or data.get("button_type", "WL"),
            button_name=data.get("buttonName") or data.get("button_name", ""),
            link_mo=data.get("linkMo") or data.get("link_mo"),
            link_pc=data.get("linkPc") or data.get("link_pc"),
            link_and=data.get("linkAnd") or data.get("link_and"),
            link_ios=data.get("linkIos") or data.get("link_ios"),
            chat_extra=data.get("chatExtra") or data.get("chat_extra"),
            target_out=bool(data.get("targetOut") or data.get("target_out", False)),
        )

    def to_dict(self) -> dict:
        return {
            "buttonType": self.button_type,
            "buttonName": self.button_name,
            "linkMo": self.link_mo,
            "linkPc": self.link_pc,
            "linkAnd": self.link_and,
            "linkIos": self.link_ios,
            "chatExtra": self.chat_extra,
            "targetOut": self.target_out,
        }


@dataclass
class KakaoTemplate:
    """Solapi 카카오 알림톡 v2 템플릿 및 로컬 템플릿 데이터 모델."""
    template_id: str
    name: str
    content: str
    variables: list[str] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    channel_id: Optional[str] = None
    channel_group_id: Optional[str] = None
    category_code: Optional[str] = None
    status: Optional[str] = None
    message_type: Optional[str] = None
    emphasize_type: Optional[str] = None
    emphasize_title: Optional[str] = None
    emphasize_subtitle: Optional[str] = None
    header: Optional[str] = None
    extra: Optional[str] = None
    ad: Optional[str] = None
    image_id: Optional[str] = None
    highlight: Optional[dict] = None
    item: Optional[dict] = None
    quick_replies: list[dict] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    code: Optional[str] = None
    security_flag: bool = False
    is_hidden: bool = False
    is_deleted: bool = False
    date_created: Optional[str] = None
    date_updated: Optional[str] = None
    is_local: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "KakaoTemplate":
        # variables 목록 정규화 ( [{"name": "이름"}] 또는 ["이름"] 형태 지원 )
        raw_vars = data.get("variables") or []
        var_names: list[str] = []
        if isinstance(raw_vars, list):
            for v in raw_vars:
                if isinstance(v, dict) and v.get("name"):
                    name = str(v["name"]).strip()
                    if name and name not in var_names:
                        var_names.append(name)
                elif isinstance(v, str):
                    name = v.strip()
                    if name and name not in var_names:
                        var_names.append(name)

        # buttons 목록 정규화
        raw_buttons = data.get("buttons") or []
        button_list: list[dict] = []
        if isinstance(raw_buttons, list):
            for b in raw_buttons:
                if isinstance(b, dict):
                    button_list.append(TemplateButton.from_dict(b).to_dict())

        tid = str(data.get("templateId") or data.get("id") or "").strip()
        name = str(data.get("name") or data.get("title") or tid).strip()

        return cls(
            template_id=tid,
            name=name,
            content=data.get("content") or "",
            variables=var_names,
            buttons=button_list,
            channel_id=data.get("channelId") or data.get("channel_id"),
            channel_group_id=data.get("channelGroupId") or data.get("channel_group_id"),
            category_code=data.get("categoryCode") or data.get("category_code"),
            status=data.get("status"),
            message_type=data.get("messageType") or data.get("message_type"),
            emphasize_type=data.get("emphasizeType") or data.get("emphasize_type"),
            emphasize_title=data.get("emphasizeTitle") or data.get("emphasize_title"),
            emphasize_subtitle=data.get("emphasizeSubtitle") or data.get("emphasize_subtitle"),
            header=data.get("header"),
            extra=data.get("extra"),
            ad=data.get("ad"),
            image_id=data.get("imageId") or data.get("image_id"),
            highlight=data.get("highlight"),
            item=data.get("item"),
            quick_replies=data.get("quickReplies") or data.get("quick_replies") or [],
            comments=data.get("comments") or [],
            code=data.get("code"),
            security_flag=bool(data.get("securityFlag") or data.get("security_flag", False)),
            is_hidden=bool(data.get("isHidden") or data.get("is_hidden", False)),
            is_deleted=bool(data.get("isDeleted") or data.get("is_deleted", False)),
            date_created=data.get("dateCreated") or data.get("date_created"),
            date_updated=data.get("dateUpdated") or data.get("date_updated"),
            is_local=bool(data.get("is_local", False) or tid.startswith("local_")),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.template_id,
            "templateId": self.template_id,
            "name": self.name,
            "title": self.name if not self.is_local else f"{self.name}",
            "content": self.content,
            "variables": self.variables,
            "buttons": self.buttons,
            "channelId": self.channel_id,
            "channelGroupId": self.channel_group_id,
            "categoryCode": self.category_code,
            "status": self.status,
            "messageType": self.message_type,
            "emphasizeType": self.emphasize_type,
            "emphasizeTitle": self.emphasize_title,
            "emphasizeSubtitle": self.emphasize_subtitle,
            "header": self.header,
            "extra": self.extra,
            "ad": self.ad,
            "imageId": self.image_id,
            "highlight": self.highlight,
            "item": self.item,
            "quickReplies": self.quick_replies,
            "comments": self.comments,
            "code": self.code,
            "securityFlag": self.security_flag,
            "isHidden": self.is_hidden,
            "isDeleted": self.is_deleted,
            "dateCreated": self.date_created,
            "dateUpdated": self.date_updated,
            "is_local": self.is_local,
        }


