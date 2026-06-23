import asyncio
from typing import Any

import pytest
from common.exceptions import BusinessException
from common.security import decode_access_token, hash_password
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.deps.auth_deps import (
    get_auth_management,
    login_check,
    permission_check,
)
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import CurrentUser, LoginRequest, RbacPermissionCache
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
    """测试用 MySQL 游标。

    用途：
        模拟 asyncmy 游标的 execute 和 fetchone 行为，只覆盖认证测试需要的查询。
    参数：
        pool：测试用连接池，内部保存用户数据。
    返回值：
        测试游标实例。
    """

    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        """记录本次 SQL 查询。

        用途：
            保存 SQL 和参数，供 fetchone 判断按账号还是按 ID 查询。
        参数：
            sql：待执行 SQL。
            params：SQL 参数。
        返回值：
            无返回值。
        """

        self.sql = sql
        self.params = params

    async def fetchone(self) -> dict[str, Any] | None:
        """返回一条用户数据。

        用途：
            根据上一次 execute 的 SQL 和参数返回测试用户。
        参数：
            无。
        返回值：
            用户字典或 None。
        """

        if "WHERE username" in self.sql:
            return self.pool.users_by_username.get(str(self.params[0]))
        if "WHERE id" in self.sql:
            return self.pool.users_by_id.get(int(self.params[0]))
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        """返回多条权限数据。

        用途：
            根据上一次 execute 的权限查询 SQL 返回测试角色拥有的权限编码。
        参数：
            无。
        返回值：
            权限字典列表。
        """

        if "FROM sys_role r" in self.sql:
            role_id = int(self.params[0])
            return [{"perm_code": code} for code in self.pool.permissions_by_role.get(role_id, [])]
        return []


class FakeConnection:
    """测试用 MySQL 连接。

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


class FakePool:
    """测试用 MySQL 连接池。

    用途：
        提供认证测试需要的最小 acquire 能力。
    参数：
        users：测试用户列表。
    返回值：
        测试连接池实例。
    """

    def __init__(
        self,
        users: list[dict[str, Any]],
        permissions_by_role: dict[int, list[str]] | None = None,
    ) -> None:
        self.users_by_username = {user["username"]: user for user in users}
        self.users_by_id = {int(user["id"]): user for user in users}
        self.permissions_by_role = permissions_by_role or {}

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
    """测试用 Redis 客户端。

    用途：
        模拟 Redis 登录态写入、读取和删除。
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
            模拟 Redis set key value ex 的登录态写入。
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

    async def delete(self, key: str) -> int:
        """删除测试缓存。

        用途：
            模拟 Redis delete。
        参数：
            key：缓存 key。
        返回值：
            删除成功返回 1，否则返回 0。
        """

        existed = key in self.values
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return 1 if existed else 0


def build_settings() -> Settings:
    """创建测试配置。

    用途：
        为认证测试提供固定 JWT 密钥和过期时间。
    参数：
        无。
    返回值：
        Settings 配置对象。
    """

    return Settings(jwt_secret_key="test-secret", jwt_access_token_expire_minutes=60)


def build_user(password: str = "secret", status: int = 1, token_version: int = 1) -> dict[str, Any]:
    """创建测试用户。

    用途：
        生成认证测试需要的用户字典和密码哈希。
    参数：
        password：明文密码，用于生成 password_hash。
        status：用户状态。
        token_version：用户 token 版本。
    返回值：
        用户字典。
    """

    return {
        "id": 1,
        "username": "admin",
        "password_hash": hash_password(password),
        "real_name": "管理员",
        "mobile": "",
        "email": "",
        "role_id": 1,
        "status": status,
        "token_version": token_version,
        "last_login_at": None,
        "created_at": None,
        "updated_at": None,
    }


def build_current_user(role_id: int = 1) -> CurrentUser:
    """创建当前登录用户。

    用途：
        为 permission_check 单元测试提供已经通过 login_check 的用户上下文。
    参数：
        role_id：当前用户所属角色 ID。
    返回值：
        CurrentUser 模型实例。
    """

    return CurrentUser(
        user_id=1,
        username="admin",
        real_name="管理员",
        role_id=role_id,
        token_version=1,
        jti="test-jti",
    )


def test_health_endpoint_still_returns_success() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "成功"


def test_login_success_writes_redis_token_state() -> None:
    async def scenario() -> None:
        settings = build_settings()
        redis_client = FakeRedis()
        manager = AuthManagement(FakePool([build_user()]), redis_client, settings)

        result = await manager.login(LoginRequest(username="admin", password="secret"))
        payload = decode_access_token(settings, result["access_token"])

        assert result["token_type"] == "bearer"
        assert result["expires_in"] == 3600
        assert result["user"]["username"] == "admin"
        assert payload["user_id"] == 1
        assert len(redis_client.values) == 1

    run_async(scenario())


def test_login_rejects_wrong_password() -> None:
    async def scenario() -> None:
        manager = AuthManagement(FakePool([build_user()]), FakeRedis(), build_settings())

        with pytest.raises(BusinessException) as exc_info:
            await manager.login(LoginRequest(username="admin", password="bad"))

        assert exc_info.value.code == 40100
        assert exc_info.value.msg == "用户名或密码错误"

    run_async(scenario())


def test_login_rejects_missing_user() -> None:
    async def scenario() -> None:
        manager = AuthManagement(FakePool([]), FakeRedis(), build_settings())

        with pytest.raises(BusinessException) as exc_info:
            await manager.login(LoginRequest(username="admin", password="secret"))

        assert exc_info.value.code == 40100
        assert exc_info.value.msg == "用户名或密码错误"

    run_async(scenario())


def test_login_check_rejects_missing_token() -> None:
    async def scenario() -> None:
        with pytest.raises(BusinessException) as exc_info:
            await login_check(
                credentials=None,
                mysql_pool=FakePool([build_user()]),
                redis_client=FakeRedis(),
                settings=build_settings(),
            )

        assert exc_info.value.code == 40100
        assert exc_info.value.msg == "缺少登录凭证"

    run_async(scenario())


def test_login_check_rejects_invalid_token() -> None:
    async def scenario() -> None:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")

        with pytest.raises(BusinessException) as exc_info:
            await login_check(
                credentials=credentials,
                mysql_pool=FakePool([build_user()]),
                redis_client=FakeRedis(),
                settings=build_settings(),
            )

        assert exc_info.value.code == 40100
        assert exc_info.value.msg == "登录凭证无效"

    run_async(scenario())


def test_permission_check_allows_cached_permission() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        cache = RbacPermissionCache(role_id=1, permissions=["user:list"])
        await redis_client.set(redis_key, cache.model_dump_json(), ex=1800)

        checker = permission_check("user:list")
        current_user = await checker(
            current_user=build_current_user(),
            mysql_pool=FakePool([build_user()]),
            redis_client=redis_client,
            settings=build_settings(),
        )

        assert current_user.user_id == 1

    run_async(scenario())


def test_permission_check_rejects_cached_missing_permission() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        cache = RbacPermissionCache(role_id=1, permissions=["role:list"])
        await redis_client.set(redis_key, cache.model_dump_json(), ex=1800)

        checker = permission_check("user:list")
        with pytest.raises(BusinessException) as exc_info:
            await checker(
                current_user=build_current_user(),
                mysql_pool=FakePool([build_user()]),
                redis_client=redis_client,
                settings=build_settings(),
            )

        assert exc_info.value.code == 40300
        assert exc_info.value.msg == "无权限访问"

    run_async(scenario())


def test_permission_check_loads_mysql_and_writes_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        checker = permission_check("user:list")

        current_user = await checker(
            current_user=build_current_user(),
            mysql_pool=FakePool([build_user()], permissions_by_role={1: ["user:list"]}),
            redis_client=redis_client,
            settings=build_settings(),
        )

        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        cache = RbacPermissionCache.model_validate_json(redis_client.values[redis_key])
        assert current_user.user_id == 1
        assert cache.permissions == ["user:list"]
        assert redis_client.expires[redis_key] == 1800

    run_async(scenario())


def test_permission_check_rejects_mysql_missing_permission() -> None:
    async def scenario() -> None:
        checker = permission_check("user:list")

        with pytest.raises(BusinessException) as exc_info:
            await checker(
                current_user=build_current_user(),
                mysql_pool=FakePool([build_user()], permissions_by_role={1: []}),
                redis_client=FakeRedis(),
                settings=build_settings(),
            )

        assert exc_info.value.code == 40300
        assert exc_info.value.msg == "无权限访问"

    run_async(scenario())


def test_permission_check_refreshes_broken_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        redis_client.values[redis_key] = "broken-json"
        checker = permission_check("user:list")

        await checker(
            current_user=build_current_user(),
            mysql_pool=FakePool([build_user()], permissions_by_role={1: ["user:list"]}),
            redis_client=redis_client,
            settings=build_settings(),
        )

        cache = RbacPermissionCache.model_validate_json(redis_client.values[redis_key])
        assert cache.permissions == ["user:list"]

    run_async(scenario())


def test_logout_deletes_only_current_token_state() -> None:
    async def scenario() -> None:
        settings = build_settings()
        redis_client = FakeRedis()
        manager = AuthManagement(FakePool([build_user()]), redis_client, settings)

        result = await manager.login(LoginRequest(username="admin", password="secret"))
        payload = decode_access_token(settings, result["access_token"])
        current_user = CurrentUser(
            user_id=1,
            username="admin",
            real_name="管理员",
            role_id=1,
            token_version=1,
            jti=payload["jti"],
        )

        await manager.logout(current_user)

        assert redis_client.values == {}

    run_async(scenario())


def test_login_endpoint_uses_unified_response_with_stub() -> None:
    class StubAuthManagement:
        """接口测试用认证业务对象。

        用途：
            替代真实 AuthManagement，验证 API 层统一响应结构。
        参数：
            无。
        返回值：
            测试业务对象实例。
        """

        async def login(self, payload: LoginRequest) -> dict[str, Any]:
            """返回固定登录结果。

            用途：
                让接口测试不依赖数据库和 Redis。
            参数：
                payload：登录请求参数。
            返回值：
                登录结果字典。
            """

            return {
                "access_token": "token",
                "token_type": "bearer",
                "expires_in": 3600,
                "user": {
                    "user_id": 1,
                    "username": payload.username,
                    "real_name": "管理员",
                    "role_id": 1,
                },
            }

    app.dependency_overrides[get_auth_management] = lambda: StubAuthManagement()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/auth/login",
                json={"username": "admin", "password": "secret"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "成功"
    assert response.json()["data"]["token_type"] == "bearer"


def test_rbac_check_endpoint_allows_user_with_permission() -> None:
    async def prepare_context() -> tuple[Settings, FakePool, FakeRedis, str]:
        settings = build_settings()
        redis_client = FakeRedis()
        mysql_pool = FakePool([build_user()], permissions_by_role={1: ["user:list"]})
        manager = AuthManagement(mysql_pool, redis_client, settings)
        result = await manager.login(LoginRequest(username="admin", password="secret"))
        return settings, mysql_pool, redis_client, result["access_token"]

    settings, mysql_pool, redis_client, token = run_async(prepare_context())
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/auth/rbac-check",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["permission"] == "user:list"


def test_rbac_check_endpoint_rejects_user_without_permission() -> None:
    async def prepare_context() -> tuple[Settings, FakePool, FakeRedis, str]:
        settings = build_settings()
        redis_client = FakeRedis()
        mysql_pool = FakePool([build_user()], permissions_by_role={1: []})
        manager = AuthManagement(mysql_pool, redis_client, settings)
        result = await manager.login(LoginRequest(username="admin", password="secret"))
        return settings, mysql_pool, redis_client, result["access_token"]

    settings, mysql_pool, redis_client, token = run_async(prepare_context())
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/auth/rbac-check",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert response.json()["msg"] == "无权限访问"
