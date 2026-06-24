from loguru import logger

from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.models.notification import CardNotificationRequest
from services.oa_admin.core.config import Settings


class RoleNotificationManagement:
    """角色通知业务对象。"""

    def __init__(
        self,
        settings: Settings,
        notification_management: NotificationManagement,
    ) -> None:
        self.settings = settings
        self.notification_management = notification_management

    async def send_role_create_notification(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在角色创建成功后发送配置化卡片通知。"""

        if not self._should_send():
            return

        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.role_notify_receive_id_type,
                    receive_id=self.settings.role_notify_receive_id,
                    card=self._build_role_create_card(data, current_user, request_id),
                    content_summary=f"角色 {data['role_code']} 创建成功",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "role create notify failed request_id={} role_code={} operator={} error={}",
                request_id,
                data["role_code"],
                current_user.username,
                exc,
            )

    async def send_role_update_notification(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在角色更新成功后发送配置化卡片通知。"""

        if not self._should_send():
            return

        change_summary = self._build_role_update_change_summary(before_data, data)
        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.role_notify_receive_id_type,
                    receive_id=self.settings.role_notify_receive_id,
                    card=self._build_role_update_card(
                        before_data,
                        data,
                        current_user,
                        request_id,
                    ),
                    content_summary=f"角色 {data['role_code']} 更新成功，{change_summary}",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "role update notify failed request_id={} role_code={} operator={} error={}",
                request_id,
                data["role_code"],
                current_user.username,
                exc,
            )

    async def send_role_assign_permission_notification(
        self,
        role: dict,
        before_permissions: list[dict],
        after_permissions: list[dict],
        current_user: CurrentUser,
        request_id: str,
    ) -> None:
        """在角色分配权限成功后发送配置化卡片通知。"""

        if not self._should_send():
            return

        change_summary = self._build_permission_change_summary(
            before_permissions,
            after_permissions,
        )
        try:
            await self.notification_management.send_card_notification(
                CardNotificationRequest(
                    receive_id_type=self.settings.role_notify_receive_id_type,
                    receive_id=self.settings.role_notify_receive_id,
                    card=self._build_role_assign_permission_card(
                        role,
                        after_permissions,
                        change_summary,
                        current_user,
                        request_id,
                    ),
                    content_summary=f"角色 {role['role_code']} 权限分配成功，{change_summary}",
                ),
                sender_user_id=current_user.user_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "role assign permission notify failed request_id={} role_code={} "
                "operator={} error={}",
                request_id,
                role["role_code"],
                current_user.username,
                exc,
            )

    def _should_send(self) -> bool:
        """判断是否需要发送角色通知。"""

        return self.settings.role_notify_enabled and bool(self.settings.role_notify_receive_id)

    def _build_role_update_change_summary(
        self,
        before_data: dict,
        data: dict,
    ) -> str:
        """生成角色更新通知中的变化摘要。"""

        labels = {
            "role_name": "名称",
            "status": "状态",
            "remark": "备注",
        }
        changes: list[str] = []
        for key, label in labels.items():
            before_value = self._render_field(key, before_data.get(key))
            after_value = self._render_field(key, data.get(key))
            if before_value != after_value:
                changes.append(f"{label}：{before_value} -> {after_value}")
        return "；".join(changes) or "无字段变化"

    def _build_permission_change_summary(
        self,
        before_permissions: list[dict],
        after_permissions: list[dict],
    ) -> str:
        """生成角色权限分配通知中的变化摘要。"""

        before_map = {int(item["id"]): item for item in before_permissions}
        after_map = {int(item["id"]): item for item in after_permissions}
        added_ids = [
            permission_id for permission_id in after_map if permission_id not in before_map
        ]
        removed_ids = [
            permission_id for permission_id in before_map if permission_id not in after_map
        ]
        changes: list[str] = []
        if added_ids:
            changes.append(
                "新增："
                + "、".join(
                    self._render_permission(after_map[permission_id])
                    for permission_id in added_ids
                )
            )
        if removed_ids:
            changes.append(
                "移除："
                + "、".join(
                    self._render_permission(before_map[permission_id])
                    for permission_id in removed_ids
                )
            )
        return "；".join(changes) or "无权限变化"

    def _build_role_create_card(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict:
        """生成角色创建成功飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "角色已成功创建。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_create_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": self._build_role_detail_content(
                            data,
                            current_user,
                            request_id,
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_create_detail",
                    },
                ],
            },
            "header": {
                "title": {"tag": "plain_text", "content": "角色创建成功"},
                "subtitle": {"tag": "plain_text", "content": ""},
                "template": "green",
                "icon": {"tag": "standard_icon", "token": "check-circle_outlined"},
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_role_update_card(
        self,
        before_data: dict,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict:
        """生成角色更新成功飞书卡片。"""

        change_summary = self._build_role_update_change_summary(before_data, data)
        detail_content = self._build_role_detail_content(
            data,
            current_user,
            request_id,
            action_text="已成功更新",
        )
        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "角色已成功更新。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_update_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": f"{detail_content}\n变更：{change_summary}",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_update_detail",
                    },
                ],
            },
            "header": {
                "title": {"tag": "plain_text", "content": "角色更新成功"},
                "subtitle": {"tag": "plain_text", "content": ""},
                "template": "blue",
                "icon": {"tag": "standard_icon", "token": "edit_outlined"},
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_role_assign_permission_card(
        self,
        role: dict,
        after_permissions: list[dict],
        change_summary: str,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict:
        """生成角色分配权限成功飞书卡片。"""

        return {
            "schema": "2.0",
            "config": {"update_multi": True},
            "body": {
                "direction": "vertical",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "角色权限已成功分配。",
                        "text_align": "left",
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_assign_permission_success_tip",
                    },
                    {
                        "tag": "markdown",
                        "content": self._build_role_permission_detail_content(
                            role,
                            after_permissions,
                            change_summary,
                            current_user,
                            request_id,
                        ),
                        "text_size": "normal",
                        "margin": "0px 0px 0px 0px",
                        "element_id": "role_assign_permission_detail",
                    },
                ],
            },
            "header": {
                "title": {"tag": "plain_text", "content": "角色权限分配成功"},
                "subtitle": {"tag": "plain_text", "content": ""},
                "template": "blue",
                "icon": {"tag": "standard_icon", "token": "setting_outlined"},
                "padding": "12px 8px 12px 8px",
            },
        }

    def _build_role_detail_content(
        self,
        data: dict,
        current_user: CurrentUser,
        request_id: str,
        action_text: str = "已成功创建",
    ) -> str:
        """生成角色卡片详情正文。"""

        return (
            f"角色 **{self._render_optional(data.get('role_name'))}** "
            f"（{self._render_optional(data.get('role_code'))}）{action_text}\n\n"
            f"角色ID：{self._render_optional(data.get('id'))}\n"
            f"状态：{self._render_status(data.get('status'))}\n"
            f"备注：{self._render_optional(data.get('remark'))}\n"
            f"操作人：{current_user.username}\n"
            f"request_id：{self._render_optional(request_id)}\n"
        )

    def _build_role_permission_detail_content(
        self,
        role: dict,
        after_permissions: list[dict],
        change_summary: str,
        current_user: CurrentUser,
        request_id: str,
    ) -> str:
        """生成角色权限分配卡片详情正文。"""

        permissions_text = self._render_permission_list(after_permissions)
        return (
            f"角色 **{self._render_optional(role.get('role_name'))}** "
            f"（{self._render_optional(role.get('role_code'))}）权限已成功分配\n\n"
            f"角色ID：{self._render_optional(role.get('id'))}\n"
            f"分配后权限：{permissions_text}\n"
            f"变更：{change_summary}\n"
            f"操作人：{current_user.username}\n"
            f"request_id：{self._render_optional(request_id)}\n"
        )

    def _render_field(self, key: str, value: object) -> str:
        """按字段类型渲染角色变化值。"""

        if key == "status":
            return self._render_status(value)
        return self._render_optional(value)

    def _render_permission(self, permission: dict) -> str:
        """渲染单个权限点。"""

        perm_name = self._render_optional(permission.get("perm_name"))
        perm_code = self._render_optional(permission.get("perm_code"))
        return f"{perm_name}（{perm_code}）"

    def _render_permission_list(self, permissions: list[dict]) -> str:
        """渲染权限点列表。"""

        if not permissions:
            return "-"
        return "、".join(self._render_permission(permission) for permission in permissions)

    def _render_status(self, status: object) -> str:
        """渲染角色状态。"""

        return "启用" if int(status) == 1 else "禁用"

    def _render_optional(self, value: object) -> str:
        """渲染卡片中的可选字段。"""

        if value is None:
            return "-"
        text = str(value).strip()
        return text or "-"
