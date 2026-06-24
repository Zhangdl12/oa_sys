from typing import Any

from common.exceptions import BusinessException

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.role.crud.role_crud import (
    get_role_by_code,
    get_role_by_id,
    insert_role,
    list_enabled_permission_ids_by_ids,
    list_permissions_by_role_id,
    list_roles,
    list_user_ids_by_role_id,
    replace_role_permissions,
    update_role,
)
from services.oa_admin.apps.role.models.role import (
    RoleAssignPermissionRequest,
    RoleCreateRequest,
    RoleInfo,
    RoleListQuery,
    RoleUpdateRequest,
)


class RoleManagement:
    """角色管理业务对象。

    用途：
        负责编排角色列表、创建、更新、分配权限和 RBAC 缓存失效。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
    返回值：
        角色管理业务对象实例。
    """

    def __init__(self, mysql_pool: Any, redis_client: Any) -> None:
        self.mysql_pool = mysql_pool
        self.redis_client = redis_client

    async def list_roles(self, query: RoleListQuery) -> list[dict[str, Any]]:
        """查询角色列表。

        用途：
            根据筛选条件查询角色，并转换为统一响应数据。
        参数：
            query：角色列表查询条件。
        返回值：
            角色字典列表。
        """

        rows = await list_roles(self.mysql_pool, keyword=query.keyword, status=query.status)
        return [RoleInfo.model_validate(row).model_dump() for row in rows]

    async def create_role(self, payload: RoleCreateRequest) -> dict[str, Any]:
        """创建角色。

        用途：
            校验角色编码唯一性后创建角色。
        参数：
            payload：创建角色请求模型。
        返回值：
            创建后的角色字典。
        """

        exists = await get_role_by_code(self.mysql_pool, payload.role_code)
        if exists:
            raise BusinessException(code=40900, msg="角色编码已存在")

        role_id = await insert_role(self.mysql_pool, payload.model_dump())
        role = await get_role_by_id(self.mysql_pool, role_id)
        return RoleInfo.model_validate(role).model_dump()

    async def get_role(self, role_id: int) -> dict[str, Any]:
        """查询单个角色。"""

        role = await get_role_by_id(self.mysql_pool, role_id)
        if not role:
            raise BusinessException(code=40400, msg="角色不存在")
        return RoleInfo.model_validate(role).model_dump()

    async def list_role_permissions(self, role_id: int) -> list[dict[str, Any]]:
        """查询角色当前权限明细。"""

        rows = await list_permissions_by_role_id(self.mysql_pool, role_id)
        return [
            {
                "id": int(row["id"]),
                "perm_code": str(row["perm_code"]),
                "perm_name": str(row.get("perm_name") or ""),
            }
            for row in rows
        ]

    async def update_role(self, role_id: int, payload: RoleUpdateRequest) -> dict[str, Any]:
        """更新角色。

        用途：
            校验角色存在后更新角色名称、状态和备注，并清理该角色用户 RBAC 缓存。
        参数：
            role_id：角色 ID。
            payload：更新角色请求模型。
        返回值：
            更新后的角色字典。
        """

        current = await get_role_by_id(self.mysql_pool, role_id)
        if not current:
            raise BusinessException(code=40400, msg="角色不存在")

        await update_role(self.mysql_pool, role_id, payload.model_dump())
        await self._clear_role_user_rbac_cache(role_id)
        role = await get_role_by_id(self.mysql_pool, role_id)
        return RoleInfo.model_validate(role).model_dump()

    async def assign_permissions(
        self,
        role_id: int,
        payload: RoleAssignPermissionRequest,
    ) -> dict[str, Any]:
        """给角色分配权限。

        用途：
            校验角色和权限有效性后，在事务内替换角色权限关联，并清理相关用户缓存。
        参数：
            role_id：角色 ID。
            payload：角色分配权限请求模型。
        返回值：
            包含角色 ID 和权限 ID 列表的字典。
        """

        role = await get_role_by_id(self.mysql_pool, role_id)
        if not role:
            raise BusinessException(code=40400, msg="角色不存在")

        permission_ids = list(dict.fromkeys(payload.permission_ids))
        enabled_permission_ids = await list_enabled_permission_ids_by_ids(
            self.mysql_pool,
            permission_ids,
        )
        if set(enabled_permission_ids) != set(permission_ids):
            raise BusinessException(code=40000, msg="权限不存在或已禁用")

        await replace_role_permissions(self.mysql_pool, role_id, permission_ids)
        await self._clear_role_user_rbac_cache(role_id)
        return {"role_id": role_id, "permission_ids": permission_ids}

    async def _clear_role_user_rbac_cache(self, role_id: int) -> None:
        """清理指定角色用户的 RBAC 缓存。

        用途：
            角色状态、角色名称或角色权限变化后，删除绑定该角色用户的权限缓存。
        参数：
            role_id：角色 ID。
        返回值：
            无返回值。
        """

        user_ids = await list_user_ids_by_role_id(self.mysql_pool, role_id)
        if not user_ids:
            return

        keys = [RBAC_USER_KEY_TEMPLATE.format(user_id=user_id) for user_id in user_ids]
        await self.redis_client.delete(*keys)
