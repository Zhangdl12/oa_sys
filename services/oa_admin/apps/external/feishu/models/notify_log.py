from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExternalNotifyLogCreate(BaseModel):
    """外部通知记录创建模型。"""

    platform: str = Field(max_length=30)
    notify_type: str = Field(max_length=30)
    receive_id_type: str = Field(max_length=30)
    receive_id: str = Field(max_length=255)
    content_summary: str = Field(default="", max_length=255)
    sender_user_id: int | None = Field(default=None, ge=1)
    request_id: str = Field(default="", max_length=64)
    result: Literal["success", "failed"]
    external_message_id: str = Field(default="", max_length=128)
    error_msg: str = Field(default="", max_length=500)


class ExternalNotifyLogListQuery(BaseModel):
    """外部通知记录列表查询模型。"""

    platform: str | None = Field(default=None, max_length=30)
    receive_id: str | None = Field(default=None, max_length=255)
    result: Literal["success", "failed"] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ExternalNotifyLogInfo(BaseModel):
    """外部通知记录返回模型。"""

    id: int
    platform: str
    notify_type: str
    receive_id_type: str
    receive_id: str
    content_summary: str
    sender_user_id: int | None
    request_id: str
    result: str
    external_message_id: str
    error_msg: str
    created_at: datetime


class ExternalNotifyLogListResponse(BaseModel):
    """外部通知记录分页响应模型。"""

    items: list[ExternalNotifyLogInfo]
    total: int
    page: int
    page_size: int
