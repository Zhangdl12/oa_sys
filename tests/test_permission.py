import asyncio
from typing import Any

import pytest
from common.exceptions import BusinessException, FeishuException
from common.security import hash_password
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import LoginRequest
from services.oa_admin.apps.external.feishu.deps.feishu_deps import get_notification_management
from services.oa_admin.apps.external.feishu.models.notification import (
    CardNotificationRequest,
    TextNotificationRequest,
)
from services.oa_admin.apps.permission.managements.permission_management import PermissionManagement
from services.oa_admin.apps.permission.models.permission import (
    PermissionCreateRequest,
    PermissionListQuery,
    PermissionUpdateRequest,
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
    """权限管理测试用 MySQL 游标。

    用途：
        模拟用户认证、RBAC 权限查询和权限点 CRUD 所需的游标行为。
    参数：
        pool：测试用连接池，保存用户、角色权限和权限点数据。
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
            记录查询 SQL，并在新增、更新权限点时直接修改测试内存数据。
        参数：
            sql：待执行 SQL。
            params：SQL 参数。
        返回值：
            无返回值。
        """

        self.sql = sql
        self.params = params
        if "INSERT INTO sys_permission" in sql:
            permission_id = self.pool.next_permission_id
            self.pool.next_permission_id += 1
            self.lastrowid = permission_id
            self.pool.permissions_by_id[permission_id] = build_permission(
                permission_id=permission_id,
                perm_code=str(params[0]),
                perm_name=str(params[1]),
                perm_type=str(params[2]),
                parent_id=int(params[3]),
                path=str(params[4]),
                method=str(params[5]),
                status=int(params[6]),
                sort=int(params[7]),
            )
        if "UPDATE sys_permission" in sql:
            permission_id = int(params[7])
            permission = self.pool.permissions_by_id[permission_id]
            permission.update(
                {
                    "perm_name": str(params[0]),
                    "perm_type": str(params[1]),
                    "parent_id": int(params[2]),
                    "path": str(params[3]),
                    "method": str(params[4]),
                    "status": int(params[5]),
                    "sort": int(params[6]),
                }
            )

    async def fetchone(self) -> dict[str, Any] | None:
        """返回一条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回用户或权限点。
        参数：
            无。
        返回值：
            数据字典或 None。
        """

        if "WHERE username" in self.sql or "WHERE u.username" in self.sql:
            return self.pool.users_by_username.get(str(self.params[0]))
        if "FROM sys_user" in self.sql and ("WHERE id" in self.sql or "WHERE u.id" in self.sql):
            return self.pool.users_by_id.get(int(self.params[0]))
        if "FROM sys_permission" in self.sql and "WHERE id" in self.sql:
            return self.pool.permissions_by_id.get(int(self.params[0]))
        if "FROM sys_permission" in self.sql and "WHERE perm_code" in self.sql:
            perm_code = str(self.params[0])
            for permission in self.pool.permissions_by_id.values():
                if permission["perm_code"] == perm_code:
                    return permission
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        """返回多条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回角色权限编码列表或权限点列表。
        参数：
            无。
        返回值：
            数据字典列表。
        """

        if "FROM sys_role r" in self.sql:
            role_id = int(self.params[0])
            codes = self.pool.permissions_by_role.get(role_id, [])
            return [{"perm_code": code} for code in codes]
        if "FROM sys_permission" in self.sql:
            permissions = list(self.pool.permissions_by_id.values())
            return sorted(permissions, key=lambda item: (int(item["sort"]), int(item["id"])))
        return []


class FakeConnection:
    """权限管理测试用 MySQL 连接。

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
    """权限管理测试用 MySQL 连接池。

    用途：
        保存认证用户、角色权限和权限点数据，并提供 acquire 方法。
    参数：
        users：测试用户列表。
        permissions：测试权限点列表。
        permissions_by_role：测试角色拥有的权限编码。
    返回值：
        测试连接池实例。
    """

    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        permissions: list[dict[str, Any]] | None = None,
        permissions_by_role: dict[int, list[str]] | None = None,
    ) -> None:
        self.users_by_username = {user["username"]: user for user in users or []}
        self.users_by_id = {int(user["id"]): user for user in users or []}
        self.permissions_by_id = {int(item["id"]): item for item in permissions or []}
        self.permissions_by_role = permissions_by_role or {}
        self.next_permission_id = max(self.permissions_by_id.keys(), default=0) + 1

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
    """权限管理测试用 Redis 客户端。

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
            模拟 Redis scan_iter，用于 RBAC 缓存批量失效。
        参数：
            match：匹配表达式，当前测试只使用前缀星号模式。
        返回值：
            异步迭代返回匹配到的 key。
        """

        prefix = match.rstrip("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key


class StubNotificationManagement:
    """权限点通知测试桩。"""

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
        return {"message_id": "om_permission_text"}

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
        return {"message_id": "om_permission_card"}


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


def build_user() -> dict[str, Any]:
    """创建测试用户。

    用途：
        生成接口认证需要的用户字典和密码哈希。
    参数：
        无。
    返回值：
        用户字典。
    """

    return {
        "id": 1,
        "username": "admin",
        "password_hash": hash_password("secret"),
        "real_name": "管理员",
        "mobile": "",
        "email": "",
        "role_id": 1,
        "status": 1,
        "token_version": 1,
    }


def build_permission(
    permission_id: int = 1,
    perm_code: str = "permission:list",
    perm_name: str = "查询权限列表",
    perm_type: str = "api",
    parent_id: int = 0,
    path: str = "/v1/permissions",
    method: str = "GET",
    status: int = 1,
    sort: int = 1,
) -> dict[str, Any]:
    """创建测试权限点。

    用途：
        生成权限管理测试需要的 sys_permission 行数据。
    参数：
        permission_id：权限点 ID。
        perm_code：权限编码。
        perm_name：权限名称。
        perm_type：权限类型。
        parent_id：父级权限 ID。
        path：接口或菜单路径。
        method：HTTP 方法。
        status：权限状态。
        sort：排序值。
    返回值：
        权限点字典。
    """

    return {
        "id": permission_id,
        "perm_code": perm_code,
        "perm_name": perm_name,
        "perm_type": perm_type,
        "parent_id": parent_id,
        "path": path,
        "method": method,
        "status": status,
        "sort": sort,
    }


def test_list_permissions_success() -> None:
    async def scenario() -> None:
        manager = PermissionManagement(
            FakePool(permissions=[build_permission()]),
            FakeRedis(),
        )

        result = await manager.list_permissions(PermissionListQuery())

        assert result[0]["perm_code"] == "permission:list"

    run_async(scenario())


def test_create_permission_success() -> None:
    async def scenario() -> None:
        manager = PermissionManagement(FakePool(), FakeRedis())

        result = await manager.create_permission(
            PermissionCreateRequest(
                perm_code="permission:create",
                perm_name="创建权限",
                perm_type="api",
                path="/v1/permissions",
                method="POST",
            )
        )

        assert result["id"] == 1
        assert result["perm_code"] == "permission:create"

    run_async(scenario())


def test_create_permission_rejects_duplicate_code() -> None:
    async def scenario() -> None:
        manager = PermissionManagement(
            FakePool(permissions=[build_permission(perm_code="permission:create")]),
            FakeRedis(),
        )

        with pytest.raises(BusinessException) as exc_info:
            await manager.create_permission(
                PermissionCreateRequest(
                    perm_code="permission:create",
                    perm_name="创建权限",
                    perm_type="api",
                )
            )

        assert exc_info.value.code == 40900
        assert exc_info.value.msg == "权限编码已存在"

    run_async(scenario())


def test_create_permission_rejects_missing_parent() -> None:
    async def scenario() -> None:
        manager = PermissionManagement(FakePool(), FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.create_permission(
                PermissionCreateRequest(
                    perm_code="permission:create",
                    perm_name="创建权限",
                    perm_type="api",
                    parent_id=999,
                )
            )

        assert exc_info.value.code == 40000
        assert exc_info.value.msg == "父级权限不存在"

    run_async(scenario())


def test_update_permission_rejects_missing_permission() -> None:
    async def scenario() -> None:
        manager = PermissionManagement(FakePool(), FakeRedis())

        with pytest.raises(BusinessException) as exc_info:
            await manager.update_permission(
                999,
                PermissionUpdateRequest(
                    perm_name="更新权限",
                    perm_type="api",
                ),
            )

        assert exc_info.value.code == 40400
        assert exc_info.value.msg == "权限不存在"

    run_async(scenario())


def test_update_permission_clears_rbac_cache() -> None:
    async def scenario() -> None:
        redis_client = FakeRedis()
        redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=1)
        await redis_client.set(
            redis_key,
            '{"role_id":1,"permissions":["permission:list"]}',
            ex=1800,
        )
        manager = PermissionManagement(
            FakePool(permissions=[build_permission()]),
            redis_client,
        )

        result = await manager.update_permission(
            1,
            PermissionUpdateRequest(
                perm_name="查询权限",
                perm_type="api",
                path="/v1/permissions",
                method="GET",
                status=0,
            ),
        )

        assert result["status"] == 0
        assert redis_key not in redis_client.values

    run_async(scenario())


def test_permission_list_api_allows_user_with_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:list"], [build_permission()])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/permissions",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"][0]["perm_code"] == "permission:list"


def test_permission_list_api_rejects_user_without_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context([], [build_permission()])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/permissions",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert response.json()["msg"] == "无权限访问"


def test_permission_create_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:create"], [])
    )
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "perm_code": "permission:create",
                    "perm_name": "创建权限",
                    "perm_type": "api",
                    "path": "/v1/permissions",
                    "method": "POST",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "成功"
    assert response.json()["data"]["perm_code"] == "permission:create"
    assert notification_management.card_payloads == []


def test_permission_create_api_sends_notification_when_enabled() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:create"], [])
    )
    settings.permission_notify_enabled = True
    settings.permission_notify_receive_id_type = "chat_id"
    settings.permission_notify_receive_id = "oc_permission"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/permissions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": "req-create-permission",
                },
                json={
                    "perm_code": "permission:create",
                    "perm_name": "创建权限",
                    "perm_type": "api",
                    "path": "/v1/permissions",
                    "method": "POST",
                    "sort": 3002,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.payloads == []
    assert notification_management.card_payloads[0].receive_id_type == "chat_id"
    assert notification_management.card_payloads[0].receive_id == "oc_permission"
    assert (
        notification_management.card_payloads[0].content_summary
        == "权限点 permission:create 创建成功"
    )
    card = notification_management.card_payloads[0].card
    content = card["body"]["elements"][1]["content"]
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "权限点创建成功"
    assert card["body"]["elements"][0]["element_id"] == "permission_create_success_tip"
    assert card["body"]["elements"][1]["element_id"] == "permission_create_detail"
    assert "权限点 **创建权限** （permission:create）" in content
    assert "权限ID：1" in content
    assert "类型：api" in content
    assert "父级ID：0" in content
    assert "路径：/v1/permissions" in content
    assert "方法：POST" in content
    assert "状态：启用" in content
    assert "排序：3002" in content
    assert "操作人：admin" in content
    assert "request_id：req-create-permission" in content
    assert notification_management.sender_user_ids[0] == 1
    assert notification_management.request_ids[0] == "req-create-permission"


def test_permission_create_api_ignores_notification_failure() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:create"], [])
    )
    settings.permission_notify_enabled = True
    settings.permission_notify_receive_id = "oc_permission"
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
                "/v1/permissions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": "req-create-notify-fail",
                },
                json={
                    "perm_code": "permission:create",
                    "perm_name": "创建权限",
                    "perm_type": "api",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["perm_code"] == "permission:create"
    assert notification_management.card_payloads[0].receive_id == "oc_permission"


def test_permission_update_api_returns_unified_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:update"], [build_permission()])
    )
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/permissions/1",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "perm_name": "查询权限",
                    "perm_type": "api",
                    "path": "/v1/permissions",
                    "method": "GET",
                    "status": 0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == 0
    assert notification_management.card_payloads == []


def test_permission_update_api_sends_notification_when_enabled() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:update"], [build_permission()])
    )
    settings.permission_notify_enabled = True
    settings.permission_notify_receive_id_type = "chat_id"
    settings.permission_notify_receive_id = "oc_permission"
    notification_management = StubNotificationManagement()
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_notification_management] = lambda: notification_management
    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/permissions/1",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": "req-update-permission",
                },
                json={
                    "perm_name": "查询权限",
                    "perm_type": "api",
                    "parent_id": 0,
                    "path": "/v1/permissions",
                    "method": "POST",
                    "status": 0,
                    "sort": 20,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert notification_management.payloads == []
    assert notification_management.card_payloads[0].receive_id_type == "chat_id"
    assert notification_management.card_payloads[0].receive_id == "oc_permission"
    assert (
        notification_management.card_payloads[0].content_summary
        == "权限点 permission:list 更新成功，名称：查询权限列表 -> 查询权限；"
        "方法：GET -> POST；状态：启用 -> 禁用；排序：1 -> 20"
    )
    card = notification_management.card_payloads[0].card
    content = card["body"]["elements"][1]["content"]
    assert card["header"]["title"]["content"] == "权限点更新成功"
    assert card["header"]["template"] == "blue"
    assert card["body"]["elements"][0]["element_id"] == "permission_update_success_tip"
    assert card["body"]["elements"][1]["element_id"] == "permission_update_detail"
    assert "权限点 **查询权限** （permission:list）" in content
    assert "方法：POST" in content
    assert "状态：禁用" in content
    assert "排序：20" in content
    assert "变更：名称：查询权限列表 -> 查询权限" in content
    assert "方法：GET -> POST" in content
    assert "状态：启用 -> 禁用" in content
    assert "排序：1 -> 20" in content
    assert "操作人：admin" in content
    assert "request_id：req-update-permission" in content
    assert notification_management.sender_user_ids[0] == 1
    assert notification_management.request_ids[0] == "req-update-permission"


def test_permission_update_api_ignores_notification_failure() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:update"], [build_permission()])
    )
    settings.permission_notify_enabled = True
    settings.permission_notify_receive_id = "oc_permission"
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
                "/v1/permissions/1",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": "req-update-notify-fail",
                },
                json={
                    "perm_name": "查询权限",
                    "perm_type": "api",
                    "path": "/v1/permissions",
                    "method": "GET",
                    "status": 0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == 0
    assert notification_management.card_payloads[0].receive_id == "oc_permission"


async def prepare_api_context(
    role_permission_codes: list[str],
    permissions: list[dict[str, Any]],
) -> tuple[Settings, FakePool, FakeRedis, str]:
    """准备权限接口测试上下文。

    用途：
        创建测试配置、Fake MySQL、Fake Redis 和可用 JWT，供接口测试复用。
    参数：
        role_permission_codes：当前用户角色拥有的权限编码。
        permissions：测试权限点列表。
    返回值：
        Settings、FakePool、FakeRedis 和 access_token。
    """

    settings = build_settings()
    redis_client = FakeRedis()
    mysql_pool = FakePool(
        users=[build_user()],
        permissions=permissions,
        permissions_by_role={1: role_permission_codes},
    )
    manager = AuthManagement(mysql_pool, redis_client, settings)
    result = await manager.login(LoginRequest(username="admin", password="secret"))
    return settings, mysql_pool, redis_client, result["access_token"]
