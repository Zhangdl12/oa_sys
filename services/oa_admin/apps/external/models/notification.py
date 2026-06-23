from typing import Any, Literal

from pydantic import BaseModel, Field


class TextNotificationRequest(BaseModel):
    """模块文本通知请求模型。

    用途：
        描述业务模块调用统一通知服务时传入的文本通知字段。
    """

    receive_id_type: Literal["open_id", "chat_id", "user_id"] = "open_id"
    receive_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=1000)
    operator: str | None = Field(default=None, max_length=100)


class CardNotificationRequest(BaseModel):
    """模块卡片通知请求模型。"""

    receive_id_type: Literal["open_id", "chat_id", "user_id"] = "open_id"
    receive_id: str = Field(min_length=1)
    card: dict[str, Any]
    content_summary: str = Field(min_length=1, max_length=255)
