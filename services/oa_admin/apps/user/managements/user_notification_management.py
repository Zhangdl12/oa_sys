from loguru import logger

from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.models.notification import (
    CardNotificationRequest,
)
from services.oa_admin.core.config import Settings


class UserNotificationManagement:
    """用户通知业务对象。

    用途：
        负责用户模块内业务场景通知的配置判断、文案组装和非阻断发送。
    参数：
        settings：系统配置对象，提供用户通知开关和接收人配置。
        notification_management：统一通知业务对象，用于实际发送通知。
    返回值：
        用户通知业务对象实例。
    """

    def __init__(
        self,
        settings: Settings,
        notification_management: NotificationManagement,
    ) -> None:
        self.settings = settings
        self.notification_management = notification_management

    async def send_user_create_notification(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在用户创建成功后发送配置化卡片通知。

        用途：
            用户创建成功后按系统配置发送飞书通知；通知失败只记录日志，不影响创建结果。
        参数：
            data：创建后的用户数据。
            current_user：permission_check 注入的当前操作用户。
            request_id：当前请求链路 ID，用于通知发送记录和问题排查。
        返回值：
            无返回值。
        """

        if not self.settings.user_create_notify_enabled:
            return
        if not self.settings.user_create_notify_receive_id:
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.user_create_notify_receive_id_type,
                    receive_id=self.settings.user_create_notify_receive_id,
                    card=self._build_user_create_card(data, current_user),
                    content_summary=f"用户 {data['username']} 创建成功",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "user create notify failed request_id={} username={} operator={} error={}",
                request_id,
                data["username"],
                current_user.username,
                exc,
            )

    async def send_user_update_notification(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在用户更新成功后发送配置化卡片通知。

        用途：
            用户角色或状态变化后按系统配置发送飞书通知；通知失败只记录日志，不影响更新结果。
        参数：
            before_data：更新前的用户数据。
            data：更新后的用户数据。
            current_user：permission_check 注入的当前操作用户。
            request_id：当前请求链路 ID，用于通知发送记录和问题排查。
        返回值：
            无返回值。
        """

        if not self.settings.user_create_notify_enabled:
            return
        if not self.settings.user_create_notify_receive_id:
            return

        change_summary = self._build_user_update_change_summary(before_data, data)
        if not change_summary:
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.user_create_notify_receive_id_type,
                    receive_id=self.settings.user_create_notify_receive_id,
                    card=self._build_user_update_card(before_data, data, current_user),
                    content_summary=f"用户 {data['username']} 更新成功，{change_summary}",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "user update notify failed request_id={} username={} operator={} error={}",
                request_id,
                data["username"],
                current_user.username,
                exc,
            )

    async def send_user_delete_notification(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在用户删除成功后发送配置化卡片通知。

        用途：
            用户删除成功后按系统配置发送飞书通知；通知失败只记录日志，不影响删除结果。
        参数：
            data：删除前的用户快照。
            current_user：permission_check 注入的当前操作用户。
            request_id：当前请求链路 ID，用于通知发送记录和问题排查。
        返回值：
            无返回值。
        """

        if not self.settings.user_create_notify_enabled:
            return
        if not self.settings.user_create_notify_receive_id:
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.user_create_notify_receive_id_type,
                    receive_id=self.settings.user_create_notify_receive_id,
                    card=self._build_user_delete_card(data, current_user),
                    content_summary=f"用户 {data['username']} 已删除",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "user delete notify failed request_id={} username={} operator={} error={}",
                request_id,
                data["username"],
                current_user.username,
                exc,
            )

    def _build_user_update_change_summary(self, before_data: dict, data: dict) -> str:
        """生成用户更新通知中的关键变化摘要。"""

        changes: list[str] = []
        if int(before_data["role_id"]) != int(data["role_id"]):
            changes.append(
                f"角色：{self._render_role(before_data)} -> {self._render_role(data)}"
            )
        if int(before_data["status"]) != int(data["status"]):
            changes.append(
                f"状态：{self._render_status(before_data['status'])} -> "
                f"{self._render_status(data['status'])}"
            )
        return "；".join(changes)

    def _build_user_update_card(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
    ) -> dict:
        """生成用户信息更新飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "ℹ️ 用户关键信息已更新。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_update_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": (
                            f"用户 **{self._render_optional(data.get('real_name'))}** "
                            f"（{self._render_optional(data.get('username'))}）信息已更新。\n\n"
                            f"🆔 用户ID：{self._render_optional(data.get('id'))}\n"
                            f"🔗 角色：{self._render_role(before_data)} -> "
                            f"{self._render_role(data)}\n"
                            f"📌 状态：{self._render_status(before_data['status'])} -> "
                            f"{self._render_status(data['status'])}\n"
                            f"👤 操作人：{current_user.username}"
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_update_detail",
                    },
                ],
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "用户信息更新",
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "",
                },
                "template": "blue",
                "icon": {
                    "tag": "standard_icon",
                    "token": "edit_outlined",
                },
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_user_delete_card(self, data: dict, current_user: CurrentUser) -> dict:
        """生成用户删除成功飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "🗑️ 用户已从系统中删除。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_delete_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": (
                            f"用户 **{self._render_optional(data.get('real_name'))}** "
                            f"（{self._render_optional(data.get('username'))}）已删除。\n\n"
                            f"🆔 用户ID：{self._render_optional(data.get('id'))}\n"
                            f"📱 手机号：{self._render_optional(data.get('mobile'))}\n"
                            f"📧 邮箱：{self._render_optional(data.get('email'))}\n"
                            f"🔗 角色：{self._render_optional(data.get('role_name'))}\n"
                            f"👤 操作人：{current_user.username}"
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_delete_detail",
                    },
                ],
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "用户删除成功",
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "",
                },
                "template": "red",
                "icon": {
                    "tag": "standard_icon",
                    "token": "delete-trash_outlined",
                },
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_user_create_card(self, data: dict, current_user: CurrentUser) -> dict:
        """生成创建用户成功飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "🎉 恭喜！新用户已成功创建。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_create_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": (
                            f"🎉 用户 **{self._render_optional(data.get('real_name'))}** "
                            f"（{self._render_optional(data.get('username'))}）已成功创建！\n\n"
                            f"🆔 用户ID：{self._render_optional(data.get('id'))}\n"
                            f"📱 手机号：{self._render_optional(data.get('mobile'))}\n"
                            f"📧 邮箱：{self._render_optional(data.get('email'))}\n"
                            f"🔗 角色：{self._render_optional(data.get('role_name'))}\n"
                            f"👤 操作人：{current_user.username}"
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "user_create_detail",
                    },
                ],
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "用户创建成功",
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "",
                },
                "template": "green",
                "icon": {
                    "tag": "standard_icon",
                    "token": "check-circle_outlined",
                },
                "padding": "12px 8px 12px 8px",
            },
        }

    def _render_optional(self, value: object) -> str:
        """渲染卡片中的可选字段。"""

        text = str(value or "").strip()
        return text or "-"

    def _render_status(self, status: object) -> str:
        """渲染用户状态值。"""

        return "启用" if int(status) == 1 else "禁用"

    def _render_role(self, data: dict) -> str:
        """渲染用户角色名称。"""

        return str(data.get("role_name") or data["role_id"])
