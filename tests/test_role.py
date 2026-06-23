import asyncio
from typing import Any

import pytest
from common.exceptions import BusinessException
from common.security import hash_password
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import LoginRequest
from services.oa_admin.apps.role.managements.role_management import RoleManagement
from services.oa_admin.apps.role.models.role import (
    RoleAssignPermissionRequest,
    RoleCreateRequest,
    RoleListQuery,
    RoleUpdateRequest,
)
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client
from services.oa_admin.main import app


def run_async(coro):
    """运行异步测试逻辑。

    用途：
        在不依赖 pytest-asyncio 插件的情况下执行 async/await 业务代码。
    参数：
        coro：需要执行的协程对象。
    返回值：
        协程执行结果。
    """

    return asyncio.run(coro)


class FakeCursor:
    """角色管理测试用 MySQL 游标。

    用途：
        模拟用户认证、RBAC 权限查询、角色 CRUD 和角色权限分配所需的游标行为。
    参数：
        pool：测试用连接池，保存用户、角色、权限和角色权限关联数据。
    返回值：
        测试游标实例。
    """

    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.lastrowid = 0

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        """执行测试 SQL。

        用途：
            记录查询 SQL，并在新增、更新角色和删除角色权限关联时修改测试内存数据。
        参数：
            sql：待执行 SQL。
            params：SQL 参数。
        返回值：
            无返回值。
        """

        self.sql = sql
        self.params = params
        if "INSERT INTO sys_role" in sql:
            role_id = self.pool.next_role_id
            self.pool.next_role_id += 1
            self.lastrowid = role_id
            self.pool.roles_by_id[role_id] = build_role(
                role_id=role_id,
                role_code=str(params[0]),
                role_name=str(params[1]),
                status=int(params[2]),
                remark=str(params[3]),
            )
        if "UPDATE sys_role" in sql:
            role_id = int(params[3])
            role = self.pool.roles_by_id[role_id]
            role.update(
                {
                    "role_name": str(params[0]),
                    "status": int(params[1]),
                    "remark": str(params[2]),
                }
            )
        if "DELETE FROM sys_role_permission" in sql:
            role_id = int(params[0])
            self.pool.role_permissions_by_role[role_id] = []

    async def executemany(self, sql: str, params: list[tuple[int, int]]) -> None:
        """批量执行测试 SQL。

        用途：
            模拟批量写入 sys_role_permission 角色权限关联。
        参数：
            sql：待执行 SQL。
            params：角色 ID 和权限 ID 参数列表。
        返回值：
            无返回值。
        """

        if "INSERT INTO sys_role_permission" not in sql:
            return
        for role_id, permission_id in params:
            self.pool.role_permissions_by_role.setdefault(role_id, []).append(permission_id)

    async def fetchone(self) -> dict[str, Any] | None:
        """返回一条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回用户或角色数据。
        参数：
            无。
        返回值：
            数据字典或 None。
        """

        if "WHERE username" in self.sql:
            return self.pool.users_by_username.get(str(self.params[0]))
        if "FROM sys_user" in self.sql and "WHERE id" in self.sql:
            return self.pool.users_by_id.get(int(self.params[0]))
        if "FROM sys_role" in self.sql and "WHERE id" in self.sql:
            return self.pool.roles_by_id.get(int(self.params[0]))
        if "FROM sys_role" in self.sql and "WHERE role_code" in self.sql:
            role_code = str(self.params[0])
            for role in self.pool.roles_by_id.values():
                if role["role_code"] == role_code:
                    return role
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        """返回多条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回角色列表、用户 ID、权限 ID 或权限编码。
        参数：
            无。
        返回值：
            数据字典列表。
        """

        if "FROM sys_role r" in self.sql:
            role_id = int(self.params[0])
            permission_ids = self.pool.role_permissions_by_role.get(role_id, [])
            return [
                {"perm_code": self.pool.permissions_by_id[permission_id]["perm_code"]}
                for permission_id in permission_ids
                if self.pool.permissions_by_id.get(permission_id, {}).get("status") == 1
            ]
        if "FROM sys_role" in self.sql:
            return sorted(self.pool.roles_by_id.values(), key=lambda item: int(item["id"]))
        if "FROM sys_user" in self.sql:
            role_id = int(self.params[0])
            return [
                {"id": user["id"]}
                for user in self.pool.users_by_id.values()
                if int(user["role_id"]) == role_id
            ]
        if "FROM sys_permission" in self.sql:
            return [
                {"id": permission_id}
                for permission_id in self.params
                if self.pool.permissions_by_id.get(int(permission_id), {}).get("status") == 1
            ]
        return []


class FakeConnection:
    """角色管理测试用 MySQL 连接。

    用途：
        模拟连接池 acquire 后返回的异步连接对象。
    参数：
        pool：测试用连接池。
    返回值：
        测试连接实例。
    """

    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    def cursor(self) -> FakeCursor:
        """创建测试游标。

        用途：
            模拟 asyncmy 连接上的 cursor 方法。
        参数：
            无。
        返回值：
            FakeCursor 实例。
        """

        return FakeCursor(self.pool)

    async def commit(self) -> None:
        """提交测试事务。

        用途：
            模拟 asyncmy 连接 commit 方法，测试数据已在 execute 阶段写入。
        参数：
            无。
        返回值：
            无返回值。
        """

        return None

    async def rollback(self) -> None:
        """回滚测试事务。

        用途：
            模拟 asyncmy 连接 rollback 方法，当前测试不触发真实数据回滚。
        参数：
            无。
        返回值：
            无返回值。
        """

        return None


class FakePool:
    """角色管理测试用 MySQL 连接池。

    用途：
        保存认证用户、角色、权限和角色权限关联数据，并提供 acquire 方法。
    参数：
        users：测试用户列表。
        roles：测试角色列表。
        permissions：测试权限点列表。
        role_permissions_by_role：测试角色权限 ID 关联。
    返回值：
        测试连接池实例。
    """

    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        roles: list[dict[str, Any]] | None = None,
        permissions: list[dict[str, Any]] | None = None,
        role_permissions_by_role: dict[int, list[int]] | None = None,
    ) -> None:
        self.users_by_username = {user["username"]: user for user in users or []}
        self.users_by_id = {int(user["id"]): user for user in users or []}
        self.roles_by_id = {int(role["id"]): role for role in roles or []}
        self.permissions_by_id = {int(item["id"]): item for item in permissions or []}
        self.role_permissions_by_role = role_permissions_by_role or {}
        self.next_role_id = max(self.roles_by_id.keys(), default=0) + 1

    def acquire(self) -> FakeConnection:
        """获取测试连接。

        用途：
            模拟 asyncmy 连接池 acquire 方法。
        参数：
            无。
        返回值：
            FakeConnection 实例。
        """

        return FakeConnection(self)


class FakeRedis:
    """角色管理测试用 Redis 客户端。

    用途：
        模拟登录态和 RBAC 权限缓存写入、读取和删除。
    参数：
        无。
    返回值：
        测试 Redis 实例。
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int) -> None:
        """写入测试缓存。

        用途：
            模拟 Redis set key value ex。
        参数：
            key：缓存 key。
            value：缓存值。
            ex：过期秒数。
        返回值：
            无返回值。
        """

        self.values[key] = value
        self.expires[key] = ex

    async def get(self, key: str) -> str | None:
        """读取测试缓存。

        用途：
            模拟 Redis get。
        参数：
            key：缓存 key。
        返回值：
            缓存字符串或 None。
        """

        return self.values.get(key)

    async def delete(self, *keys: str) -> int:
        """删除测试缓存。

        用途：
            模拟 Redis delete，支持一次删除多个 key。
        参数：
            keys：待删除的缓存 key。
        返回值：
            实际删除的 key 数量。
        """

        count = 0
        for key in keys:
            if key in self.values:
                count += 1
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return count


def build_settings() -> Settings:
    """创建测试配置。

    用途：
        为接口测试提供固定 JWT 密钥和过期时间。
    参数：
        无。
    返回值：
        Settings 配置对象。
    """

    return Settings(jwt_secret_key="test-secret", jwt_access_token_expire_minutes=60)


def build_user(user_id: int = 1, role_id: int = 1) -> dict[str, Any]:
    """创建测试用户。

    用途：
        生成接口认证和角色缓存清理测试需要的用户字典。
    参数：
        user_id：用户 ID。
        role_id：用户所属角色 ID。
    返回值：
        用户字典。
    """

    return {
        "id": user_id,
        "username": "admin" if user_id == 1 else f"user{user_id}",
        "password_hash": hash_password("secret"),
        "real_name": "管理员",
        "role_id": role_id,
        "status": 1,
        "token_version": 1,
    }


def build_role(
    role_id: int = 1,
    role_code: str = "admin",
    role_name: str = "管理员",
    status: int = 1,
    remark: str = "",
) -> dict[str, Any]:
    """创建测试角色。

    用途：
        生成角色管理测试需要的 sys_role 行数据。
    参数：
        role_id：角色 ID。
        role_code：角色编码。
        role_name：角色名称。
        status：角色状态。
        remark：角色备注。
    返回值：
        角色字典。
    """

    return {
        "id": role_id,
        "role_code": role_code,
        "role_name": role_name,
        "status": status,
        "remark": remark,
    }


def build_permission(
    permission_id: int,
    perm_code: str,
    status: int = 1,
) -> dict[str, Any]:
    """创建测试权限点。

    用途：
        生成角色权限分配和接口权限校验需要的权限点数据。
    参数：
        permission_id：权限点 ID。
        perm_code：权限编码。
        status：权限状态。
    返回值：
        权限点字典。
    """

    return {"id": permission_id, "perm_code": perm_code, "status": status}


def test_list_roles_success() -> None:
    async def scenario() -> None:
        manager = RoleManagement(
            FakePool(roles=[build_role(role_id=2, role_code="staff", role_name="员工")]),
            FakeRedis(),
        )

        result = await manager.list_roles(RoleListQuery())

        assert result[0]["role_code"] == "staff"

    run_async(scenario())


def test_create_role_success() -> None:
    async def scenario() -> None:
        manager = RoleManagement(FakePool(), FakeRedis())

        result = await manager.create_role(
            RoleCreateRequest(role_code="staff", role_name="员工")
        )

        assert result["id"] == 1
        assert result["role_code"] == "staff"

    run_async(scenario())


def test_create_role_rejects_duplicate_code() -> None:
    async def scenario() -> None:
        manager = RoleManagement(
            FakePool(roles=[build_role(role_code="staff")]),
            FakeRedis(),
        )

        with pytest.raises(BusinessException) as exc_info:
            await manager.create_role(RoleCreateRequest(role_code="staff", role_name="员工"))

        assert exc_info.value.code == 40900
        assert exc_info.value.msg == "角色编码已存在"

    run_async(scenario())


def test_update_role_rejects_missing_role() -> None:
    async def scenario() -> None:
        manager = RoleManagement(FakePool(), FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.update_role(999, RoleUpdateRequest(role_name="员工"))

        assert exc_info.value.code == 40400
        assert exc_info.value.msg == "角色不存在"

    run_async(scenario())


def test_update_role_clears_role_user_rbac_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        await redis_client.set(redis_key, '{"role_id":2,"permissions":["role:list"]}', ex=1800)
        manager = RoleManagement(
            FakePool(
                users=[build_user(role_id=2)],
                roles=[build_role(role_id=2, role_code="staff")],
            ),
            redis_client,
        )

        result = await manager.update_role(
            2,
            RoleUpdateRequest(role_name="员工", status=0, remark="停用"),
        )

        assert result["status"] == 0
        assert redis_key not in redis_client.values

    run_async(scenario())


def test_assign_permissions_replaces_old_permissions() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        await redis_client.set(redis_key, '{"role_id":2,"permissions":["role:list"]}', ex=1800)
        pool = FakePool(
            users=[build_user(role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
            permissions=[
                build_permission(10, "role:list"),
                build_permission(11, "role:create"),
            ],
            role_permissions_by_role={2: [10]},
        )
        manager = RoleManagement(pool, redis_client)

        result = await manager.assign_permissions(
            2,
            RoleAssignPermissionRequest(permission_ids=[11]),
        )

        assert result == {"role_id": 2, "permission_ids": [11]}
        assert pool.role_permissions_by_role[2] == [11]
        assert redis_key not in redis_client.values

    run_async(scenario())


def test_assign_permissions_rejects_missing_or_disabled_permission() -> None:
    async def scenario() -> None:
        manager = RoleManagement(
            FakePool(
                roles=[build_role(role_id=2, role_code="staff")],
                permissions=[build_permission(10, "role:list", status=0)],
            ),
            FakeRedis(),
        )

        with pytest.raises(BusinessException) as exc_info:
            await manager.assign_permissions(
                2,
                RoleAssignPermissionRequest(permission_ids=[10]),
            )

        assert exc_info.value.code == 40000
        assert exc_info.value.msg == "权限不存在或已禁用"

    run_async(scenario())


def test_role_list_api_allows_user_with_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["role:list"], roles=[build_role(role_id=2, role_code="staff")])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/v1/roles", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    role_codes = {item["role_code"] for item in response.json()["data"]}
    assert "staff" in role_codes


def test_role_list_api_rejects_user_without_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context([], roles=[build_role(role_id=2, role_code="staff")])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/v1/roles", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert response.json()["msg"] == "无权限访问"


def test_role_create_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["role:create"], roles=[build_role()])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_code": "staff", "role_name": "员工"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "成功"
    assert response.json()["data"]["role_code"] == "staff"


def test_role_update_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["role:update"],
            roles=[build_role(role_id=2, role_code="staff")],
            users=[build_user(role_id=1)],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/roles/2",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_name": "员工", "status": 0, "remark": "停用"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == 0


def test_role_assign_permission_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["role:assign_permission"],
            roles=[build_role(role_id=2, role_code="staff")],
            permissions=[build_permission(10, "role:list")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/roles/2/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission_ids": [10]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {"role_id": 2, "permission_ids": [10]}


async def prepare_api_context(
    auth_permission_codes: list[str],
    roles: list[dict[str, Any]],
    permissions: list[dict[str, Any]] | None = None,
    users: list[dict[str, Any]] | None = None,
) -> tuple[Settings, FakePool, FakeRedis, str]:
    """准备角色接口测试上下文。

    用途：
        创建测试配置、Fake MySQL、Fake Redis 和可用 JWT，供接口测试复用。
    参数：
        auth_permission_codes：当前用户角色拥有的权限编码。
        roles：测试角色列表。
        permissions：测试权限点列表。
        users：测试用户列表。
    返回值：
        Settings、FakePool、FakeRedis 和 access_token。
    """

    settings = build_settings()
    redis_client = FakeRedis()
    auth_permissions = [
        build_permission(index + 1000, perm_code)
        for index, perm_code in enumerate(auth_permission_codes)
    ]
    all_permissions = auth_permissions + (permissions or [])
    auth_permission_ids = [int(permission["id"]) for permission in auth_permissions]
    mysql_pool = FakePool(
        users=users or [build_user(role_id=1)],
        roles=[build_role(role_id=1, role_code="admin")] + roles,
        permissions=all_permissions,
        role_permissions_by_role={1: auth_permission_ids},
    )
    manager = AuthManagement(mysql_pool, redis_client, settings)
    result = await manager.login(LoginRequest(username="admin", password="secret"))
    return settings, mysql_pool, redis_client, result["access_token"]
