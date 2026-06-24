from typing import Any, Literal

from pydantic import BaseModel, Field


class FeishuNotifyRequest(BaseModel):
    """飞书文本通知请求。"""

    receive_id_type: Literal["open_id", "chat_id", "user_id"] = "open_id"
    receive_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class FeishuCardNotifyRequest(BaseModel):
    """飞书卡片通知请求。"""

    receive_id_type: Literal["open_id", "chat_id", "user_id"] = "open_id"
    receive_id: str = Field(min_length=1)
    card: dict[str, Any]
    content_summary: str = Field(min_length=1, max_length=255)
