from typing import Any

from common.exceptions import BusinessException
from common.external.feishu import FeishuClient

from services.oa_admin.apps.external.crud.notify_log_crud import insert_notify_log
from services.oa_admin.apps.external.models.feishu import (
    FeishuCardNotifyRequest,
    FeishuNotifyRequest,
)
from services.oa_admin.apps.external.models.notify_log import ExternalNotifyLogCreate
from services.oa_admin.core.config import Settings


class FeishuManagement:
    """飞书集成业务对象。

    用途：
        编排飞书配置校验、tenant_access_token 获取、文本消息发送和发送记录写入。
    """

    def __init__(
        self,
        http_client: Any,
        redis_client: Any,
        mysql_pool: Any,
        settings: Settings,
    ) -> None:
        self.http_client = http_client
        self.redis_client = redis_client
        self.mysql_pool = mysql_pool
        self.settings = settings
        self.client = FeishuClient(
            http_client=http_client,
            base_url=settings.feishu_base_url,
        )

    async def send_text_notify(
        self,
        payload: FeishuNotifyRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        """发送飞书文本通知并记录发送结果。

        参数：
            payload：飞书文本通知请求参数。
            sender_user_id：发起发送的后台用户 ID。
            request_id：当前请求链路 ID。
        返回值：
            飞书消息发送接口返回的结果。
        """

        try:
            if not self.settings.feishu_enabled:
                raise BusinessException(code=40000, msg="飞书集成未启用")
            if not self.settings.feishu_app_id or not self.settings.feishu_app_secret:
                raise BusinessException(code=40000, msg="飞书应用配置缺失")

            token = await self.client.get_cached_tenant_access_token(
                redis_client=self.redis_client,
                app_name=self.settings.app_name,
                app_id=self.settings.feishu_app_id,
                app_secret=self.settings.feishu_app_secret,
            )
            result = await self.client.send_text_message(
                tenant_access_token=token,
                receive_id_type=payload.receive_id_type,
                receive_id=payload.receive_id,
                text=payload.text,
            )
            await self._write_notify_log(
                payload=payload,
                sender_user_id=sender_user_id,
                request_id=request_id,
                result="success",
                external_message_id=self._extract_message_id(result),
                error_msg="",
            )
            return result
        except Exception as exc:
            await self._write_notify_log(
                payload=payload,
                sender_user_id=sender_user_id,
                request_id=request_id,
                result="failed",
                external_message_id="",
                error_msg=self._build_error_msg(exc),
            )
            raise

    async def send_card_notify(
        self,
        payload: FeishuCardNotifyRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        """发送飞书卡片通知并记录发送结果。"""

        try:
            if not self.settings.feishu_enabled:
                raise BusinessException(code=40000, msg="飞书集成未启用")
            if not self.settings.feishu_app_id or not self.settings.feishu_app_secret:
                raise BusinessException(code=40000, msg="飞书应用配置缺失")

            token = await self.client.get_cached_tenant_access_token(
                redis_client=self.redis_client,
                app_name=self.settings.app_name,
                app_id=self.settings.feishu_app_id,
                app_secret=self.settings.feishu_app_secret,
            )
            result = await self.client.send_card_message(
                tenant_access_token=token,
                receive_id_type=payload.receive_id_type,
                receive_id=payload.receive_id,
                card=payload.card,
            )
            await self._write_notify_log(
                payload=payload,
                sender_user_id=sender_user_id,
                request_id=request_id,
                result="success",
                external_message_id=self._extract_message_id(result),
                error_msg="",
            )
            return result
        except Exception as exc:
            await self._write_notify_log(
                payload=payload,
                sender_user_id=sender_user_id,
                request_id=request_id,
                result="failed",
                external_message_id="",
                error_msg=self._build_error_msg(exc),
            )
            raise

    async def _write_notify_log(
        self,
        payload: FeishuNotifyRequest | FeishuCardNotifyRequest,
        sender_user_id: int | None,
        request_id: str,
        result: str,
        external_message_id: str,
        error_msg: str,
    ) -> None:
        """写入飞书通知发送记录。

        用途：
            将成功或失败结果落到 sys_external_notify_log，便于后台查询和排查。
        """

        log = ExternalNotifyLogCreate(
            platform="feishu",
            notify_type=self._get_notify_type(payload),
            receive_id_type=payload.receive_id_type,
            receive_id=payload.receive_id,
            content_summary=self._get_content_summary(payload),
            sender_user_id=sender_user_id,
            request_id=request_id,
            result=result,
            external_message_id=external_message_id,
            error_msg=error_msg[:500],
        )
        await insert_notify_log(self.mysql_pool, log.model_dump())

    def _get_notify_type(self, payload: FeishuNotifyRequest | FeishuCardNotifyRequest) -> str:
        """获取通知记录类型。"""

        if isinstance(payload, FeishuCardNotifyRequest):
            return "card"
        return "text"

    def _get_content_summary(self, payload: FeishuNotifyRequest | FeishuCardNotifyRequest) -> str:
        """获取通知记录正文摘要。"""

        if isinstance(payload, FeishuCardNotifyRequest):
            return payload.content_summary[:255]
        return payload.text[:255]

    def _extract_message_id(self, result: dict[str, Any]) -> str:
        """从飞书发送结果中提取 message_id。"""

        data = result.get("data")
        if isinstance(data, dict):
            return str(data.get("message_id") or "")
        return ""

    def _build_error_msg(self, exc: Exception) -> str:
        """生成通知记录中保存的失败原因摘要。"""

        if isinstance(exc, BusinessException):
            return exc.msg
        return str(exc)
