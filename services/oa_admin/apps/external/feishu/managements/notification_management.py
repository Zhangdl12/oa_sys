from typing import Any

from services.oa_admin.apps.external.feishu.managements.feishu_management import FeishuManagement
from services.oa_admin.apps.external.feishu.models.feishu import (
    FeishuCardNotifyRequest,
    FeishuNotifyRequest,
)
from services.oa_admin.apps.external.feishu.models.notification import (
    CardNotificationRequest,
    TextNotificationRequest,
)


class NotificationManagement:
    """统一通知业务对象。

    用途：
        将业务模块传入的通知字段转换成平台发送请求，避免业务模块直接拼飞书请求体。
    """

    def __init__(self, feishu_management: FeishuManagement) -> None:
        self.feishu_management = feishu_management

    async def send_text_notification(
        self,
        payload: TextNotificationRequest,
        request_id: str,
        sender_user_id: int | None,
    ) -> dict[str, Any]:
        """发送模块文本通知。

        参数：
            payload：模块文本通知请求。
            request_id：当前请求链路 ID。
            sender_user_id：发起发送的后台用户 ID。
        返回值：
            飞书文本通知发送结果。
        """

        text = self._render_text(payload)
        feishu_payload = FeishuNotifyRequest(
            receive_id_type=payload.receive_id_type,
            receive_id=payload.receive_id,
            text=text,
        )
        return await self.feishu_management.send_text_notify(
            feishu_payload,
            sender_user_id=sender_user_id,
            request_id=request_id,
        )

    async def send_card_notification(
        self,
        payload: CardNotificationRequest,
        request_id: str,
        sender_user_id: int | None,
    ) -> dict[str, Any]:
        """发送模块卡片通知。"""

        feishu_payload = FeishuCardNotifyRequest(
            receive_id_type=payload.receive_id_type,
            receive_id=payload.receive_id,
            card=payload.card,
            content_summary=payload.content_summary,
        )
        return await self.feishu_management.send_card_notify(
            feishu_payload,
            sender_user_id=sender_user_id,
            request_id=request_id,
        )

    def _render_text(self, payload: TextNotificationRequest) -> str:
        """将模块通知字段渲染成最终飞书文本。"""

        lines = [f"【{payload.title}】{payload.content}"]
        if payload.operator:
            lines.append(f"操作人：{payload.operator}")
        return "\n".join(lines)
