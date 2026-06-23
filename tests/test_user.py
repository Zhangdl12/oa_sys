import asyncio
from typing import Any

import pytest
from common.exceptions import BusinessException, FeishuException
from common.security import hash_password, verify_password
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.constants import LOGIN_USER_KEY_PATTERN, RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import LoginRequest
from services.oa_admin.apps.external.deps.external_deps import get_notification_management
from services.oa_admin.apps.external.models.notification import (
    CardNotificationRequest,
    TextNotificationRequest,
)
from services.oa_admin.apps.user.managements.user_management import UserManagement
from services.oa_admin.apps.user.models.user import (
    UserCreateRequest,
    UserListQuery,
    UserUpdateRequest,
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
    """用户管理测试用 MySQL 游标。

    用途：
        模拟认证、权限校验、用户 CRUD 和角色校验所需的游标行为。
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
            记录 SQL，并在新增、更新和删除用户时修改测试内存数据。
        参数：
            sql：待执行 SQL。
            params：SQL 参数。
        返回值：
            无返回值。
        """

        self.sql = sql
        self.params = params
        if "INSERT INTO sys_user" in sql:
            user_id = self.pool.next_user_id
            self.pool.next_user_id += 1
            self.lastrowid = user_id
            user = build_user(
                user_id=user_id,
                username=str(params[0]),
                password_hash=str(params[1]),
                real_name=str(params[2]),
                mobile=str(params[3]),
                email=str(params[4]),
                role_id=int(params[5]),
                status=int(params[6]),
            )
            self.pool.users_by_id[user_id] = user
            self.pool.users_by_username[user["username"]] = user
        if "UPDATE sys_user" in sql and "SET real_name" in sql:
            user_id = int(params[5])
            user = self.pool.users_by_id[user_id]
            user.update(
                {
                    "real_name": str(params[0]),
                    "mobile": str(params[1]),
                    "email": str(params[2]),
                    "role_id": int(params[3]),
                    "status": int(params[4]),
                }
            )
            if "token_version = token_version + 1" in sql:
                user["token_version"] = int(user["token_version"]) + 1
        if "DELETE FROM sys_user" in sql:
            user_id = int(params[0])
            user = self.pool.users_by_id.pop(user_id, None)
            if user is not None:
                self.pool.users_by_username.pop(str(user["username"]), None)

    async def fetchone(self) -> dict[str, Any] | None:
        """返回一条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回用户或角色数据。
        参数：
            无。
        返回值：
            数据字典或 None。
        """

        if "COUNT(*) AS total" in self.sql and "FROM sys_user u" in self.sql:
            role_code = str(self.params[0])
            total = 0
            for user in self.pool.users_by_id.values():
                role = self.pool.roles_by_id.get(int(user["role_id"]))
                if (
                    role
                    and role["role_code"] == role_code
                    and int(role["status"]) == 1
                    and int(user["status"]) == 1
                ):
                    total += 1
            return {"total": total}
        if "WHERE u.username" in self.sql or "WHERE username" in self.sql:
            return self.pool.with_role_name(self.pool.users_by_username.get(str(self.params[0])))
        if "FROM sys_user" in self.sql and ("WHERE u.id" in self.sql or "WHERE id" in self.sql):
            return self.pool.with_role_name(self.pool.users_by_id.get(int(self.params[0])))
        if "FROM sys_role" in self.sql and "WHERE id" in self.sql:
            return self.pool.roles_by_id.get(int(self.params[0]))
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        """返回多条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回用户列表或当前角色权限编码列表。
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
        if "FROM sys_user" in self.sql:
            return [
                self.pool.with_role_name(user)
                for user in sorted(self.pool.users_by_id.values(), key=lambda item: int(item["id"]))
            ]
        return []


class FakeConnection:
    """用户管理测试用 MySQL 连接。

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


class FakePool:
    """用户管理测试用 MySQL 连接池。

    用途：
        保存用户、角色、权限和角色权限关联数据，并提供 acquire 方法。
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
        self.next_user_id = max(self.users_by_id.keys(), default=0) + 1

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

    def with_role_name(self, user: dict[str, Any] | None) -> dict[str, Any] | None:
        """为测试用户补充角色名称。"""

        if user is None:
            return None
        result = dict(user)
        role = self.roles_by_id.get(int(result["role_id"]))
        result["role_code"] = str(role.get("role_code") or "") if role else ""
        result["role_name"] = str(role.get("role_name") or "") if role else ""
        return result


class FakeRedis:
    """用户管理测试用 Redis 客户端。

    用途：
        模拟登录态、RBAC 权限缓存写入、读取、扫描和删除。
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

    async def scan_iter(self, match: str):
        """扫描测试缓存 key。

        用途：
            模拟 Redis scan_iter，只支持当前测试需要的前缀星号匹配。
        参数：
            match：匹配表达式，例如 oa:login:1:*。
        返回值：
            异步生成器，逐个返回匹配的 key。
        """

        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key


class StubNotificationManagement:
    """用户创建通知测试桩。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.payloads: list[TextNotificationRequest] = []
        self.card_payloads: list[CardNotificationRequest] = []
        self.sender_user_ids: list[int | None] = []
        self.request_ids: list[str] = []

    async def send_text_notification(
        self,
        payload: TextNotificationRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        if self.error is not None:
            raise self.error
        return {"message_id": "om_user_create"}

    async def send_card_notification(
        self,
        payload: CardNotificationRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.card_payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        if self.error is not None:
            raise self.error
        return {"message_id": "om_user_create_card"}


def build_settings(**kwargs: Any) -> Settings:
    """创建测试配置。

    用途：
        为接口测试提供固定 JWT 密钥和过期时间。
    参数：
        无。
    返回值：
        Settings 配置对象。
    """

    return Settings(
        jwt_secret_key="test-secret",
        jwt_access_token_expire_minutes=60,
        **kwargs,
    )


def build_user(
    user_id: int = 1,
    username: str = "admin",
    password_hash: str | None = None,
    real_name: str = "管理员",
    mobile: str = "",
    email: str = "",
    role_id: int = 1,
    status: int = 1,
    token_version: int = 1,
) -> dict[str, Any]:
    """创建测试用户。

    用途：
        生成用户管理和接口认证测试需要的 sys_user 行数据。
    参数：
        user_id：用户 ID。
        username：登录账号。
        password_hash：密码哈希，为空时使用 secret 生成。
        real_name：真实姓名。
        mobile：手机号。
        email：邮箱。
        role_id：用户所属角色 ID。
        status：用户状态。
        token_version：Token 版本。
    返回值：
        用户字典。
    """

    return {
        "id": user_id,
        "username": username,
        "password_hash": password_hash or hash_password("secret"),
        "real_name": real_name,
        "mobile": mobile,
        "email": email,
        "role_id": role_id,
        "status": status,
        "token_version": token_version,
    }


def build_role(
    role_id: int = 1,
    role_code: str = "admin",
    role_name: str = "管理员",
    status: int = 1,
) -> dict[str, Any]:
    """创建测试角色。

    用途：
        生成用户创建、用户更新和接口权限校验需要的 sys_role 行数据。
    参数：
        role_id：角色 ID。
        role_code：角色编码。
        role_name：角色名称。
        status：角色状态。
    返回值：
        角色字典。
    """

    return {
        "id": role_id,
        "role_code": role_code,
        "role_name": role_name,
        "status": status,
        "remark": "",
    }


def build_permission(
    permission_id: int,
    perm_code: str,
    status: int = 1,
) -> dict[str, Any]:
    """创建测试权限点。

    用途：
        生成接口权限校验需要的权限点数据。
    参数：
        permission_id：权限点 ID。
        perm_code：权限编码。
        status：权限状态。
    返回值：
        权限点字典。
    """

    return {"id": permission_id, "perm_code": perm_code, "status": status}


def test_list_users_success() -> None:
    async def scenario() -> None:
        manager = UserManagement(
            FakePool(
                users=[
                    build_user(),
                    build_user(user_id=2, username="staff", real_name="员工", role_id=2),
                ],
                roles=[build_role(), build_role(role_id=2, role_code="staff")],
            ),
            FakeRedis(),
        )

        result = await manager.list_users(UserListQuery())

        assert [item["username"] for item in result] == ["admin", "staff"]
        assert "password_hash" not in result[0]

    run_async(scenario())


def test_get_user_success() -> None:
    async def scenario() -> None:
        manager = UserManagement(FakePool(users=[build_user()]), FakeRedis())

        result = await manager.get_user(1)

        assert result["username"] == "admin"
        assert "password_hash" not in result

    run_async(scenario())


def test_create_user_success_hashes_password() -> None:
    async def scenario() -> None:
        pool = FakePool(roles=[build_role(role_id=2, role_code="staff")])
        manager = UserManagement(pool, FakeRedis())

        result = await manager.create_user(
            UserCreateRequest(username="staff", password="secret123", role_id=2)
        )

        created = pool.users_by_id[int(result["id"])]
        assert result["username"] == "staff"
        assert "password_hash" not in result
        assert created["password_hash"] != "secret123"
        assert verify_password("secret123", str(created["password_hash"]))

    run_async(scenario())


def test_create_user_rejects_duplicate_username() -> None:
    async def scenario() -> None:
        manager = UserManagement(
            FakePool(users=[build_user(username="staff")], roles=[build_role()]),
            FakeRedis(),
        )

        with pytest.raises(BusinessException) as exc_info:
            await manager.create_user(
                UserCreateRequest(username="staff", password="secret", role_id=1)
            )

        assert exc_info.value.code == 40900
        assert exc_info.value.msg == "用户名已存在"

    run_async(scenario())


def test_create_user_rejects_missing_or_disabled_role() -> None:
    async def scenario() -> None:
        manager = UserManagement(
            FakePool(roles=[build_role(role_id=2, status=0)]),
            FakeRedis(),
        )

        with pytest.raises(BusinessException) as exc_info:
            await manager.create_user(
                UserCreateRequest(username="staff", password="secret", role_id=2)
            )

        assert exc_info.value.code == 40000
        assert exc_info.value.msg == "角色不存在或已禁用"

    run_async(scenario())


def test_update_user_rejects_missing_user() -> None:
    async def scenario() -> None:
        manager = UserManagement(FakePool(roles=[build_role()]), FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.update_user(999, UserUpdateRequest(role_id=1))

        assert exc_info.value.code == 40400
        assert exc_info.value.msg == "用户不存在"

    run_async(scenario())


def test_update_user_role_or_status_clears_auth_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        rbac_key = RBAC_USER_KEY_TEMPLATE.format(user_id=2)
        login_key = LOGIN_USER_KEY_PATTERN.format(user_id=2).replace("*", "jti-1")
        await redis_client.set(rbac_key, '{"role_id":2,"permissions":["user:list"]}', ex=1800)
        await redis_client.set(login_key, '{"token_digest":"digest"}', ex=3600)
        pool = FakePool(
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[
                build_role(role_id=2, role_code="staff", role_name="员工"),
                build_role(role_id=3, role_code="manager", role_name="主管"),
            ],
        )
        manager = UserManagement(pool, redis_client)

        result = await manager.update_user(
            2,
            UserUpdateRequest(real_name="主管", role_id=3, status=1),
        )

        assert result["role_id"] == 3
        assert result["token_version"] == 2
        assert rbac_key not in redis_client.values
        assert login_key not in redis_client.values

    run_async(scenario())


def test_delete_user_removes_user_and_clears_auth_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        rbac_key = RBAC_USER_KEY_TEMPLATE.format(user_id=2)
        login_key = LOGIN_USER_KEY_PATTERN.format(user_id=2).replace("*", "jti-1")
        await redis_client.set(rbac_key, '{"role_id":2,"permissions":["user:list"]}', ex=1800)
        await redis_client.set(login_key, '{"token_digest":"digest"}', ex=3600)
        pool = FakePool(
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
        manager = UserManagement(pool, redis_client)

        result = await manager.delete_user(2, operator_user_id=1)

        assert result["username"] == "staff"
        assert 2 not in pool.users_by_id
        assert "staff" not in pool.users_by_username
        assert rbac_key not in redis_client.values
        assert login_key not in redis_client.values

    run_async(scenario())


def test_delete_user_rejects_current_login_user() -> None:
    async def scenario() -> None:
        pool = FakePool(
            users=[build_user(user_id=1, username="admin", role_id=1)],
            roles=[build_role(role_id=1, role_code="super_admin")],
        )
        manager = UserManagement(pool, FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.delete_user(1, operator_user_id=1)

        assert exc_info.value.code == 40000
        assert exc_info.value.msg == "不能删除当前登录用户"
        assert 1 in pool.users_by_id

    run_async(scenario())


def test_delete_user_rejects_last_enabled_super_admin() -> None:
    async def scenario() -> None:
        pool = FakePool(
            users=[build_user(user_id=1, username="admin", role_id=1)],
            roles=[build_role(role_id=1, role_code="super_admin")],
        )
        manager = UserManagement(pool, FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.delete_user(1, operator_user_id=99)

        assert exc_info.value.code == 40000
        assert exc_info.value.msg == "不能删除最后一个超级管理员"
        assert 1 in pool.users_by_id

    run_async(scenario())


def test_delete_user_allows_super_admin_when_another_enabled_exists() -> None:
    async def scenario() -> None:
        pool = FakePool(
            users=[
                build_user(user_id=1, username="admin", role_id=1),
                build_user(user_id=2, username="admin2", role_id=1),
            ],
            roles=[build_role(role_id=1, role_code="super_admin")],
        )
        manager = UserManagement(pool, FakeRedis())

        result = await manager.delete_user(2, operator_user_id=1)

        assert result["username"] == "admin2"
        assert 2 not in pool.users_by_id
        assert "admin2" not in pool.users_by_username

    run_async(scenario())


def test_user_list_api_allows_user_with_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:list"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/v1/users", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    usernames = {item["username"] for item in response.json()["data"]}
    assert "staff" in usernames


def test_user_list_api_rejects_user_without_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            [],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/v1/users", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert response.json()["msg"] == "无权限访问"


def test_user_create_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["user:create"], roles=[build_role(role_id=2, role_code="staff")])
    )
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/users",
                headers={"Authorization": f"Bearer {token}"},
                json={"username": "staff", "password": "secret123", "role_id": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "成功"
    assert response.json()["data"]["username"] == "staff"
    assert "password_hash" not in response.json()["data"]
    assert notification_management.payloads == []


def test_user_create_api_sends_notification_when_enabled() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:create"],
            roles=[build_role(role_id=2, role_code="staff", role_name="员工")],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id_type = "chat_id"
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/users",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-create-user"},
                json={
                    "username": "staff",
                    "password": "secret123",
                    "real_name": "员工",
                    "mobile": "13800000000",
                    "email": "staff@example.com",
                    "role_id": 2,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.payloads == []
    assert notification_management.card_payloads[0].receive_id_type == "chat_id"
    assert notification_management.card_payloads[0].receive_id == "oc_notify"
    assert notification_management.card_payloads[0].content_summary == "用户 staff 创建成功"
    card = notification_management.card_payloads[0].card
    content = card["body"]["elements"][1]["content"]
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "用户创建成功"
    assert card["body"]["elements"][0]["element_id"] == "user_create_success_tip"
    assert card["body"]["elements"][1]["element_id"] == "user_create_detail"
    assert "用户 **员工** （staff）已成功创建" in content
    assert f"用户ID：{response.json()['data']['id']}" in content
    assert "手机号：13800000000" in content
    assert "邮箱：staff@example.com" in content
    assert "角色：员工" in content
    assert "操作人：admin" in content
    assert notification_management.sender_user_ids[0] == 1
    assert notification_management.request_ids[0] == "req-create-user"


def test_user_create_api_sends_notification_to_user_id() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["user:create"], roles=[build_role(role_id=2, role_code="staff")])
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id_type = "user_id"
    settings.user_create_notify_receive_id = "d93addgc"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/users",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-create-user"},
                json={"username": "staff", "password": "secret123", "role_id": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.card_payloads[0].receive_id_type == "user_id"
    assert notification_management.card_payloads[0].receive_id == "d93addgc"


def test_user_create_api_ignores_notification_failure() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["user:create"], roles=[build_role(role_id=2, role_code="staff")])
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement(
        error=FeishuException(msg="send failed")
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/users",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-notify-fail"},
                json={"username": "staff", "password": "secret123", "role_id": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["username"] == "staff"
    assert notification_management.card_payloads[0].receive_id == "oc_notify"


def test_user_update_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:update"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}"},
                json={"real_name": "员工", "mobile": "", "email": "", "role_id": 2, "status": 0},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == 0


def test_user_update_api_omits_notification_for_profile_only_change() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:update"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "real_name": "员工A",
                    "mobile": "13800000000",
                    "email": "staff@example.com",
                    "role_id": 2,
                    "status": 1,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.payloads == []


def test_user_update_api_sends_notification_for_role_or_status_change() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:update"],
            users=[build_user(user_id=2, username="staff", role_id=2, status=1)],
            roles=[
                build_role(role_id=2, role_code="staff", role_name="员工"),
                build_role(role_id=3, role_code="manager", role_name="主管"),
            ],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id_type = "chat_id"
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-update-user"},
                json={
                    "real_name": "主管",
                    "mobile": "",
                    "email": "",
                    "role_id": 3,
                    "status": 0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.payloads == []
    assert notification_management.card_payloads[0].receive_id_type == "chat_id"
    assert notification_management.card_payloads[0].receive_id == "oc_notify"
    assert (
        notification_management.card_payloads[0].content_summary
        == "用户 staff 更新成功，角色：员工 -> 主管；状态：启用 -> 禁用"
    )
    card = notification_management.card_payloads[0].card
    content = card["body"]["elements"][1]["content"]
    assert card["header"]["title"]["content"] == "用户信息更新"
    assert card["header"]["template"] == "blue"
    assert card["body"]["elements"][0]["element_id"] == "user_update_success_tip"
    assert card["body"]["elements"][1]["element_id"] == "user_update_detail"
    assert "用户 **主管** （staff）信息已更新" in content
    assert "角色：员工 -> 主管" in content
    assert "状态：启用 -> 禁用" in content
    assert "操作人：admin" in content
    assert notification_management.sender_user_ids[0] == 1
    assert notification_management.request_ids[0] == "req-update-user"


def test_user_update_api_ignores_notification_failure() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:update"],
            users=[build_user(user_id=2, username="staff", role_id=2, status=1)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement(
        error=FeishuException(msg="send failed")
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-update-fail"},
                json={
                    "real_name": "员工",
                    "mobile": "",
                    "email": "",
                    "role_id": 2,
                    "status": 0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == 0
    assert notification_management.card_payloads[0].receive_id == "oc_notify"


def test_user_delete_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:delete"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["username"] == "staff"
    assert 2 not in mysql_pool.users_by_id
    assert "staff" not in mysql_pool.users_by_username


def test_user_delete_api_rejects_current_login_user() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["user:delete"])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/v1/users/1",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40000
    assert response.json()["msg"] == "不能删除当前登录用户"
    assert 1 in mysql_pool.users_by_id


def test_user_delete_api_sends_notification_when_enabled() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:delete"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id_type = "chat_id"
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-delete-user"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["username"] == "staff"
    assert 2 not in mysql_pool.users_by_id
    assert notification_management.payloads == []
    assert notification_management.card_payloads[0].receive_id_type == "chat_id"
    assert notification_management.card_payloads[0].receive_id == "oc_notify"
    assert notification_management.card_payloads[0].content_summary == "用户 staff 已删除"
    card = notification_management.card_payloads[0].card
    content = card["body"]["elements"][1]["content"]
    assert card["header"]["title"]["content"] == "用户删除成功"
    assert card["header"]["template"] == "red"
    assert card["body"]["elements"][0]["element_id"] == "user_delete_success_tip"
    assert card["body"]["elements"][1]["element_id"] == "user_delete_detail"
    assert "用户 **管理员** （staff）已删除" in content
    assert "用户ID：2" in content
    assert "角色：管理员" in content
    assert "操作人：admin" in content
    assert notification_management.sender_user_ids[0] == 1
    assert notification_management.request_ids[0] == "req-delete-user"


def test_user_delete_api_ignores_notification_failure() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:delete"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    settings.user_create_notify_enabled = True
    settings.user_create_notify_receive_id = "oc_notify"
    notification_management = StubNotificationManagement(
        error=FeishuException(msg="send failed")
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/v1/users/2",
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-delete-fail"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["username"] == "staff"
    assert 2 not in mysql_pool.users_by_id
    assert notification_management.card_payloads[0].receive_id == "oc_notify"


async def prepare_api_context(
    auth_permission_codes: list[str],
    users: list[dict[str, Any]] | None = None,
    roles: list[dict[str, Any]] | None = None,
) -> tuple[Settings, FakePool, FakeRedis, str]:
    """准备用户接口测试上下文。

    用途：
        创建测试配置、Fake MySQL、Fake Redis 和可用 JWT，供接口测试复用。
    参数：
        auth_permission_codes：当前用户角色拥有的权限编码。
        users：业务接口测试需要的用户列表。
        roles：业务接口测试需要的角色列表。
    返回值：
        Settings、FakePool、FakeRedis 和 access_token。
    """

    settings = build_settings()
    redis_client = FakeRedis()
    admin_user = build_user()
    all_users = [admin_user]
    all_users.extend(users or [])
    auth_permissions = [
        build_permission(index + 1000, perm_code)
        for index, perm_code in enumerate(auth_permission_codes)
    ]
    auth_permission_ids = [int(permission["id"]) for permission in auth_permissions]
    mysql_pool = FakePool(
        users=all_users,
        roles=[build_role()] + (roles or []),
        permissions=auth_permissions,
        role_permissions_by_role={1: auth_permission_ids},
    )
    manager = AuthManagement(mysql_pool, redis_client, settings)
    result = await manager.login(LoginRequest(username="admin", password="secret"))
    return settings, mysql_pool, redis_client, result["access_token"]
