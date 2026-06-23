from loguru import logger

from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.models.notification import CardNotificationRequest
from services.oa_admin.core.config import Settings


class PermissionNotificationManagement:
    """权限点通知业务对象。

    用途：
        负责权限点创建、更新后的配置判断、卡片组装和非阻断发送。
    参数：
        settings：系统配置对象，提供权限通知开关和接收人配置。
        notification_management：统一通知业务对象，用于实际发送通知。
    返回值：
        权限点通知业务对象实例。
    """

    def __init__(
        self,
        settings: Settings,
        notification_management: NotificationManagement,
    ) -> None:
        self.settings = settings
        self.notification_management = notification_management

    async def send_permission_create_notification(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在权限点创建成功后发送配置化卡片通知。"""

        if not self._should_send():
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.permission_notify_receive_id_type,
                    receive_id=self.settings.permission_notify_receive_id,
                    card=self._build_permission_create_card(data, current_user, request_id),
                    content_summary=f"权限点 {data['perm_code']} 创建成功",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "permission create notify failed request_id={} perm_code={} "
                "operator={} error={}",
                request_id,
                data["perm_code"],
                current_user.username,
                exc,
            )

    async def send_permission_update_notification(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在权限点更新成功后发送配置化卡片通知。"""

        if not self._should_send():
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.permission_notify_receive_id_type,
                    receive_id=self.settings.permission_notify_receive_id,
                    card=self._build_permission_update_card(
                        before_data,
                        data,
                        current_user,
                        request_id,
                    ),
                    content_summary=(
                        f"权限点 {data['perm_code']} 更新成功，"
                        f"{self._build_permission_update_change_summary(before_data, data)}"
                    ),
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "permission update notify failed request_id={} perm_code={} "
                "operator={} error={}",
                request_id,
                data["perm_code"],
                current_user.username,
                exc,
            )

    def _should_send(self) -> bool:
        """判断是否需要发送权限点通知。"""

        return (
            self.settings.permission_notify_enabled
            and bool(self.settings.permission_notify_receive_id)
        )

    def _build_permission_update_change_summary(
        self,
        before_data: dict,
        data: dict,
    ) -> str:
        """生成权限点更新通知中的变化摘要。"""

        labels = {
            "perm_name": "名称",
            "perm_type": "类型",
            "parent_id": "父级",
            "path": "路径",
            "method": "方法",
            "status": "状态",
            "sort": "排序",
        }
        changes: list[str] = []
        for key, label in labels.items():
            before_value = self._render_field(key, before_data.get(key))
            after_value = self._render_field(key, data.get(key))
            if before_value != after_value:
                changes.append(f"{label}：{before_value} -> {after_value}")
        return "；".join(changes) or "无字段变化"

    def _build_permission_create_card(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict:
        """生成权限点创建成功飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "权限点已成功创建。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "permission_create_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": self._build_permission_detail_content(
                            data,
                            current_user,
                            request_id,
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "permission_create_detail",
                    },
                ],
            },
            "header": {
                "title": {"tag": "plain_text", "content": "权限点创建成功"},
                "subtitle": {"tag": "plain_text", "content": ""},
                "template": "green",
                "icon": {"tag": "standard_icon", "token": "check-circle_outlined"},
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_permission_update_card(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict:
        """生成权限点更新成功飞书卡片。"""

        change_summary = self._build_permission_update_change_summary(before_data, data)
        detail_content = self._build_permission_detail_content(data, current_user, request_id)
        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "权限点已成功更新。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "permission_update_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": f"{detail_content}\n变更：{change_summary}",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "permission_update_detail",
                    },
                ],
            },
            "header": {
                "title": {"tag": "plain_text", "content": "权限点更新成功"},
                "subtitle": {"tag": "plain_text", "content": ""},
                "template": "blue",
                "icon": {"tag": "standard_icon", "token": "edit_outlined"},
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_permission_detail_content(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> str:
        """生成权限点卡片详情正文。"""

        return (
            f"权限点 **{self._render_optional(data.get('perm_name'))}** "
            f"（{self._render_optional(data.get('perm_code'))}）\n\n"
            f"权限ID：{self._render_optional(data.get('id'))}\n"
            f"类型：{self._render_optional(data.get('perm_type'))}\n"
            f"父级ID：{self._render_optional(data.get('parent_id'))}\n"
            f"路径：{self._render_optional(data.get('path'))}\n"
            f"方法：{self._render_optional(data.get('method'))}\n"
            f"状态：{self._render_status(data.get('status'))}\n"
            f"排序：{self._render_optional(data.get('sort'))}\n"
            f"操作人：{current_user.username}\n"
            f"request_id：{self._render_optional(request_id)}\n"
        )

    def _render_field(self, key: str, value: object) -> str:
        """按字段类型渲染权限点变化值。"""

        if key == "status":
            return self._render_status(value)
        return self._render_optional(value)

    def _render_status(self, status: object) -> str:
        """渲染权限状态值。"""

        return "启用" if int(status) == 1 else "禁用"

    def _render_optional(self, value: object) -> str:
        """渲染卡片中的可选字段。"""

        if value is None:
            return "-"
        text = str(value).strip()
        return text or "-"
