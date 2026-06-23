from typing import Any

from common.exceptions import BusinessException
from common.security import hash_password

from services.oa_admin.apps.auth.constants import LOGIN_USER_KEY_PATTERN, RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.role.crud.role_crud import get_role_by_id
from services.oa_admin.apps.user.crud.user_crud import (
    count_enabled_users_by_role_code,
    get_user_by_id,
    get_user_by_username,
    insert_user,
    list_users,
    update_user,
)
from services.oa_admin.apps.user.crud.user_crud import (
    delete_user as delete_user_row,
)
from services.oa_admin.apps.user.models.user import (
    UserCreateRequest,
    UserInfo,
    UserListQuery,
    UserUpdateRequest,
)


class UserManagement:
    """用户管理业务对象。

    用途：
        负责编排用户列表、详情、创建、更新、删除和登录态缓存失效。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
    返回值：
        用户管理业务对象实例。
    """

    def __init__(self, mysql_pool: Any, redis_client: Any) -> None:
        self.mysql_pool = mysql_pool
        self.redis_client = redis_client

    async def list_users(self, query: UserListQuery) -> list[dict[str, Any]]:
        """查询用户列表。

        用途：
            根据筛选条件查询用户，并转换为统一响应数据。
        参数：
            query：用户列表查询条件。
        返回值：
            用户字典列表。
        """

        rows = await list_users(
            self.mysql_pool,
            keyword=query.keyword,
            status=query.status,
            role_id=query.role_id,
        )
        return [UserInfo.model_validate(row).model_dump() for row in rows]

    async def get_user(self, user_id: int) -> dict[str, Any]:
        """查询用户详情。

        用途：
            按用户 ID 查询用户详情，并隐藏 password_hash。
        参数：
            user_id：用户 ID。
        返回值：
            用户详情字典。
        """

        user = await get_user_by_id(self.mysql_pool, user_id)
        if not user:
            raise BusinessException(code=40400, msg="用户不存在")
        return UserInfo.model_validate(user).model_dump()

    async def create_user(self, payload: UserCreateRequest) -> dict[str, Any]:
        """创建用户。

        用途：
            校验用户名唯一性和角色有效性后创建用户，并写入密码哈希。
        参数：
            payload：创建用户请求模型。
        返回值：
            创建后的用户字典。
        """

        exists = await get_user_by_username(self.mysql_pool, payload.username)
        if exists:
            raise BusinessException(code=40900, msg="用户名已存在")

        await self._check_enabled_role(payload.role_id)
        user_payload = payload.model_dump(exclude={"password"})
        user_payload["password_hash"] = hash_password(payload.password)
        user_id = await insert_user(self.mysql_pool, user_payload)
        user = await get_user_by_id(self.mysql_pool, user_id)
        return UserInfo.model_validate(user).model_dump()

    async def update_user(self, user_id: int, payload: UserUpdateRequest) -> dict[str, Any]:
        """更新用户。

        用途：
            校验用户和角色后更新用户资料；角色或状态变化时强制旧 token 失效。
        参数：
            user_id：用户 ID。
            payload：更新用户请求模型。
        返回值：
            更新后的用户字典。
        """

        current = await get_user_by_id(self.mysql_pool, user_id)
        if not current:
            raise BusinessException(code=40400, msg="用户不存在")

        await self._check_enabled_role(payload.role_id)
        force_logout = (
            int(current["role_id"]) != payload.role_id or int(current["status"]) != payload.status
        )
        await update_user(
            self.mysql_pool,
            user_id,
            payload.model_dump(),
            increase_token_version=force_logout,
        )
        if force_logout:
            await self._clear_user_auth_cache(user_id)

        user = await get_user_by_id(self.mysql_pool, user_id)
        return UserInfo.model_validate(user).model_dump()

    async def delete_user(self, user_id: int, operator_user_id: int) -> dict[str, Any]:
        """删除用户。

        用途：
            校验删除保护规则后执行用户真实删除，并清理该用户所有登录态和权限缓存。
        参数：
            user_id：用户 ID。
            operator_user_id：当前操作用户 ID。
        返回值：
            删除前的用户快照字典。
        """

        if user_id == operator_user_id:
            raise BusinessException(code=40000, msg="不能删除当前登录用户")

        current = await get_user_by_id(self.mysql_pool, user_id)
        if not current:
            raise BusinessException(code=40400, msg="用户不存在")

        if await self._is_last_enabled_super_admin(current):
            raise BusinessException(code=40000, msg="不能删除最后一个超级管理员")

        data = UserInfo.model_validate(current).model_dump()
        await delete_user_row(self.mysql_pool, user_id)
        await self._clear_user_auth_cache(user_id)
        return data

    async def _is_last_enabled_super_admin(self, user: dict[str, Any]) -> bool:
        """判断目标用户是否为最后一个启用的超级管理员。"""

        if str(user.get("role_code") or "") != "super_admin":
            return False
        if int(user["status"]) != 1:
            return False
        total = await count_enabled_users_by_role_code(self.mysql_pool, "super_admin")
        return total <= 1

    async def _check_enabled_role(self, role_id: int) -> None:
        """校验角色是否存在且启用。

        用途：
            创建或更新用户前确认角色可用，避免用户绑定禁用角色。
        参数：
            role_id：角色 ID。
        返回值：
            无返回值。
        """

        role = await get_role_by_id(self.mysql_pool, role_id)
        if not role or int(role["status"]) != 1:
            raise BusinessException(code=40000, msg="角色不存在或已禁用")

    async def _clear_user_auth_cache(self, user_id: int) -> None:
        """清理用户认证和权限缓存。

        用途：
            用户角色或状态变化后，删除该用户所有登录态和 RBAC 权限缓存。
        参数：
            user_id：用户 ID。
        返回值：
            无返回值。
        """

        keys: list[str] = [RBAC_USER_KEY_TEMPLATE.format(user_id=user_id)] #  缓存权限
        login_key_pattern = LOGIN_USER_KEY_PATTERN.format(user_id=user_id) #  缓存登录态
        async for key in self.redis_client.scan_iter(match=login_key_pattern):
            keys.append(str(key))
        await self.redis_client.delete(*keys)
