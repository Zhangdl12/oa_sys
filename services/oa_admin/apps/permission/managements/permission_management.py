from typing import Any

from common.exceptions import BusinessException

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_PATTERN
from services.oa_admin.apps.permission.crud.permission_crud import (
    get_permission_by_code,
    get_permission_by_id,
    insert_permission,
    list_permissions,
    update_permission,
)
from services.oa_admin.apps.permission.models.permission import (
    PermissionCreateRequest,
    PermissionInfo,
    PermissionListQuery,
    PermissionUpdateRequest,
)


class PermissionManagement:
    """权限点管理业务对象。

    用途：
        负责编排权限点列表、创建、更新、父级校验和 RBAC 缓存失效。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
    返回值：
        权限点管理业务对象实例。
    """

    def __init__(self, mysql_pool: Any, redis_client: Any) -> None:
        self.mysql_pool = mysql_pool
        self.redis_client = redis_client

    async def list_permissions(self, query: PermissionListQuery) -> list[dict[str, Any]]:
        """查询权限点列表。

        用途：
            根据筛选条件查询权限点，并转换为统一响应数据。
        参数：
            query：权限列表查询条件。
        返回值：
            权限点字典列表。
        """

        rows = await list_permissions(
            self.mysql_pool,
            keyword=query.keyword,
            perm_type=query.perm_type,
            status=query.status,
            parent_id=query.parent_id,
        )
        return [PermissionInfo.model_validate(row).model_dump() for row in rows]

    async def get_permission(self, permission_id: int) -> dict[str, Any]:
        """查询单个权限点。

        用途：
            根据权限点 ID 查询权限点详情，供接口更新前生成变更快照使用。
        参数：
            permission_id：权限点 ID。
        返回值：
            权限点字典。
        """

        permission = await get_permission_by_id(self.mysql_pool, permission_id)
        if not permission:
            raise BusinessException(code=40400, msg="权限不存在")
        return PermissionInfo.model_validate(permission).model_dump()

    async def create_permission(self, payload: PermissionCreateRequest) -> dict[str, Any]:
        """创建权限点。

        用途：
            校验权限编码唯一性和父级权限存在性后创建权限点。
        参数：
            payload：创建权限点请求模型。
        返回值：
            创建后的权限点字典。
        """

        exists = await get_permission_by_code(self.mysql_pool, payload.perm_code)
        if exists:
            raise BusinessException(code=40900, msg="权限编码已存在")

        await self._check_parent_permission(payload.parent_id)
        permission_id = await insert_permission(self.mysql_pool, payload.model_dump())
        permission = await get_permission_by_id(self.mysql_pool, permission_id)
        return PermissionInfo.model_validate(permission).model_dump()

    async def update_permission(
        self,
        permission_id: int,
        payload: PermissionUpdateRequest,
    ) -> dict[str, Any]:
        """更新权限点。

        用途：
            校验权限点和父级权限后更新权限点，并清理 RBAC 权限缓存。
        参数：
            permission_id：权限点 ID。
            payload：更新权限点请求模型。
        返回值：
            更新后的权限点字典。
        """

        current = await get_permission_by_id(self.mysql_pool, permission_id)
        if not current:
            raise BusinessException(code=40400, msg="权限不存在")
        if payload.parent_id == permission_id:
            raise BusinessException(code=40000, msg="父级权限不能是自己")

        await self._check_parent_permission(payload.parent_id)
        await update_permission(self.mysql_pool, permission_id, payload.model_dump())
        await self._clear_rbac_cache()

        permission = await get_permission_by_id(self.mysql_pool, permission_id)
        return PermissionInfo.model_validate(permission).model_dump()

    async def _check_parent_permission(self, parent_id: int) -> None:
        """校验父级权限是否存在。

        用途：
            当 parent_id 非 0 时，确认父级权限点存在，避免形成无效层级。
        参数：
            parent_id：父级权限 ID。
        返回值：
            无返回值。
        """

        if parent_id == 0:
            return
        parent = await get_permission_by_id(self.mysql_pool, parent_id)
        if not parent:
            raise BusinessException(code=40000, msg="父级权限不存在")

    async def _clear_rbac_cache(self) -> None:
        """清理 RBAC 用户权限缓存。

        用途：
            权限点更新后删除所有用户权限缓存，避免继续使用旧权限状态。
        参数：
            无。
        返回值：
            无返回值。
        """

        keys: list[str] = []
        async for key in self.redis_client.scan_iter(match=RBAC_USER_KEY_PATTERN):
            keys.append(str(key))
        if keys:
            await self.redis_client.delete(*keys)
