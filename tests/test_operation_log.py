import asyncio
from datetime import datetime
from typing import Any

import pytest
from common.exceptions import BusinessException
from common.security import hash_password
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import LoginRequest
from services.oa_admin.apps.operation_log.managements.operation_log_management import (
    OperationLogManagement,
)
from services.oa_admin.apps.operation_log.models.operation_log import (
    OperationLogCreate,
    OperationLogListQuery,
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
    """操作日志测试用 MySQL 游标。

    用途：
        模拟认证、RBAC、操作日志查询写入，以及用户、角色、权限写接口所需 SQL。
    参数：
        pool：测试用连接池，保存内存数据。
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
            记录 SQL，并在新增操作日志、用户、角色和权限点时修改内存数据。
        参数：
            sql：待执行 SQL。
            params：SQL 参数。
        返回值：
            无返回值。
        """

        self.sql = sql
        self.params = params
        if "INSERT INTO sys_operation_log" in sql:
            if self.pool.fail_operation_log_insert:
                raise RuntimeError("operation log insert failed")
            log_id = self.pool.next_log_id
            self.pool.next_log_id += 1
            self.lastrowid = log_id
            self.pool.operation_logs_by_id[log_id] = build_operation_log(
                log_id=log_id,
                user_id=int(params[0]),
                request_id=str(params[1]),
                action=str(params[2]),
                path=str(params[3]),
                method=str(params[4]),
                ip=str(params[5]),
                result=str(params[6]),
            )
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

    async def fetchone(self) -> dict[str, Any] | None:
        """返回一条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回用户、角色、权限点或操作日志数据。
        参数：
            无。
        返回值：
            数据字典或 None。
        """

        if "COUNT(*) AS total" in self.sql:
            return {"total": len(self.pool.operation_logs_by_id)}
        if "FROM sys_operation_log" in self.sql and "WHERE id" in self.sql:
            return self.pool.operation_logs_by_id.get(int(self.params[0]))
        if "WHERE username" in self.sql or "WHERE u.username" in self.sql:
            return self.pool.users_by_username.get(str(self.params[0]))
        if "FROM sys_user" in self.sql and (
            "WHERE id" in self.sql or "WHERE u.id" in self.sql
        ):
            return self.pool.users_by_id.get(int(self.params[0]))
        if "FROM sys_role" in self.sql and "WHERE id" in self.sql:
            return self.pool.roles_by_id.get(int(self.params[0]))
        if "FROM sys_role" in self.sql and "WHERE role_code" in self.sql:
            for role in self.pool.roles_by_id.values():
                if role["role_code"] == str(self.params[0]):
                    return role
        if "FROM sys_permission" in self.sql and "WHERE id" in self.sql:
            return self.pool.permissions_by_id.get(int(self.params[0]))
        if "FROM sys_permission" in self.sql and "WHERE perm_code" in self.sql:
            for permission in self.pool.permissions_by_id.values():
                if permission["perm_code"] == str(self.params[0]):
                    return permission
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        """返回多条测试数据。

        用途：
            根据上一次 execute 的 SQL 返回权限编码或操作日志分页数据。
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
        if "FROM sys_operation_log" in self.sql:
            logs = sorted(
                self.pool.operation_logs_by_id.values(),
                key=lambda item: int(item["id"]),
                reverse=True,
            )
            if len(self.params) >= 2:
                limit = int(self.params[-2])
                offset = int(self.params[-1])
                return logs[offset : offset + limit]
            return logs
        return []


class FakeConnection:
    """操作日志测试用 MySQL 连接。

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
    """操作日志测试用 MySQL 连接池。

    用途：
        保存认证用户、角色、权限和操作日志数据，并提供 acquire 方法。
    参数：
        users：测试用户列表。
        roles：测试角色列表。
        permissions：测试权限点列表。
        role_permissions_by_role：测试角色权限 ID 关联。
        operation_logs：测试操作日志列表。
        fail_operation_log_insert：是否模拟操作日志写入失败。
    返回值：
        测试连接池实例。
    """

    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        roles: list[dict[str, Any]] | None = None,
        permissions: list[dict[str, Any]] | None = None,
        role_permissions_by_role: dict[int, list[int]] | None = None,
        operation_logs: list[dict[str, Any]] | None = None,
        fail_operation_log_insert: bool = False,
    ) -> None:
        self.users_by_username = {user["username"]: user for user in users or []}
        self.users_by_id = {int(user["id"]): user for user in users or []}
        self.roles_by_id = {int(role["id"]): role for role in roles or []}
        self.permissions_by_id = {int(item["id"]): item for item in permissions or []}
        self.role_permissions_by_role = role_permissions_by_role or {}
        self.operation_logs_by_id = {int(item["id"]): item for item in operation_logs or []}
        self.fail_operation_log_insert = fail_operation_log_insert
        self.next_user_id = max(self.users_by_id.keys(), default=0) + 1
        self.next_role_id = max(self.roles_by_id.keys(), default=0) + 1
        self.next_permission_id = max(self.permissions_by_id.keys(), default=0) + 1
        self.next_log_id = max(self.operation_logs_by_id.keys(), default=0) + 1

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
    """操作日志测试用 Redis 客户端。

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

    async def scan_iter(self, match: str):
        """扫描测试缓存 key。

        用途：
            模拟 Redis scan_iter，当前测试不依赖扫描结果。
        参数：
            match：匹配表达式。
        返回值：
            异步生成器，当前不返回任何 key。
        """

        if False:
            yield match


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
        生成认证和用户写接口测试需要的 sys_user 行数据。
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
    remark: str = "",
) -> dict[str, Any]:
    """创建测试角色。

    用途：
        生成认证、角色写接口和用户角色校验需要的 sys_role 行数据。
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
    perm_name: str = "权限",
    perm_type: str = "api",
    parent_id: int = 0,
    path: str = "",
    method: str = "",
    status: int = 1,
    sort: int = 0,
) -> dict[str, Any]:
    """创建测试权限点。

    用途：
        生成接口权限校验和权限点写接口测试需要的权限点数据。
    参数：
        permission_id：权限点 ID。
        perm_code：权限编码。
        perm_name：权限名称。
        perm_type：权限类型。
        parent_id：父级权限 ID。
        path：接口路径。
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


def build_operation_log(
    log_id: int = 1,
    user_id: int = 1,
    request_id: str = "req-1",
    action: str = "创建用户",
    path: str = "/v1/users",
    method: str = "POST",
    ip: str = "127.0.0.1",
    result: str = "成功",
) -> dict[str, Any]:
    """创建测试操作日志。

    用途：
        生成操作日志查询和详情测试需要的 sys_operation_log 行数据。
    参数：
        log_id：操作日志 ID。
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        ip：客户端 IP。
        result：操作结果。
    返回值：
        操作日志字典。
    """

    return {
        "id": log_id,
        "user_id": user_id,
        "request_id": request_id,
        "action": action,
        "path": path,
        "method": method,
        "ip": ip,
        "result": result,
        "created_at": datetime(2026, 6, 21, 12, 0, 0),
    }


def test_list_operation_logs_success() -> None:
    async def scenario() -> None:
        manager = OperationLogManagement(
            FakePool(
                operation_logs=[
                    build_operation_log(log_id=1, action="创建用户"),
                    build_operation_log(log_id=2, action="更新用户"),
                ],
            )
        )

        result = await manager.list_operation_logs(OperationLogListQuery(page=1, page_size=1))

        assert result["total"] == 2
        assert result["page"] == 1
        assert result["page_size"] == 1
        assert result["items"][0]["id"] == 2

    run_async(scenario())


def test_get_operation_log_success() -> None:
    async def scenario() -> None:
        manager = OperationLogManagement(
            FakePool(operation_logs=[build_operation_log(log_id=1, action="创建用户")])
        )

        result = await manager.get_operation_log(1)

        assert result["id"] == 1
        assert result["action"] == "创建用户"

    run_async(scenario())


def test_get_operation_log_rejects_missing_log() -> None:
    async def scenario() -> None:
        manager = OperationLogManagement(FakePool())

        with pytest.raises(BusinessException) as exc_info:
            await manager.get_operation_log(999)

        assert exc_info.value.code == 40400
        assert exc_info.value.msg == "操作日志不存在"

    run_async(scenario())


def test_create_operation_log_success() -> None:
    async def scenario() -> None:
        pool = FakePool()
        manager = OperationLogManagement(pool)

        log_id = await manager.create_operation_log(
            OperationLogCreate(
                user_id=1,
                request_id="req-1",
                action="创建用户",
                path="/v1/users",
                method="POST",
                ip="127.0.0.1",
                result="成功",
            )
        )

        assert log_id == 1
        assert pool.operation_logs_by_id[1]["action"] == "创建用户"

    run_async(scenario())


def test_operation_log_list_api_allows_user_with_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["operation_log:list"],
            operation_logs=[build_operation_log(log_id=1)],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/operation-logs",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["total"] == 1


def test_operation_log_list_api_rejects_user_without_permission() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context([], operation_logs=[build_operation_log(log_id=1)])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/operation-logs",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert response.json()["msg"] == "无权限访问"


def test_user_create_api_writes_success_operation_log() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:create"],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
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
    assert len(mysql_pool.operation_logs_by_id) == 1
    log = next(iter(mysql_pool.operation_logs_by_id.values()))
    assert log["action"] == "创建用户"
    assert log["result"] == "成功"


def test_role_create_api_writes_success_operation_log() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["role:create"])
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
    log = next(iter(mysql_pool.operation_logs_by_id.values()))
    assert log["action"] == "创建角色"
    assert log["result"] == "成功"


def test_permission_create_api_writes_success_operation_log() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(["permission:create"])
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "perm_code": "demo:create",
                    "perm_name": "创建演示",
                    "perm_type": "api",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    log = next(iter(mysql_pool.operation_logs_by_id.values()))
    assert log["action"] == "创建权限点"
    assert log["result"] == "成功"


def test_write_api_business_exception_writes_failed_operation_log() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:create"],
            users=[build_user(user_id=2, username="staff", role_id=2)],
            roles=[build_role(role_id=2, role_code="staff")],
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
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
    assert response.json()["code"] == 40900
    log = next(iter(mysql_pool.operation_logs_by_id.values()))
    assert log["action"] == "创建用户"
    assert log["result"] == "失败"


def test_operation_log_write_failure_does_not_block_api_response() -> None:
    settings, mysql_pool, redis_client, token = run_async(
        prepare_api_context(
            ["user:create"],
            roles=[build_role(role_id=2, role_code="staff")],
            fail_operation_log_insert=True,
        )
    )
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings
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
    assert mysql_pool.operation_logs_by_id == {}


async def prepare_api_context(
    auth_permission_codes: list[str],
    users: list[dict[str, Any]] | None = None,
    roles: list[dict[str, Any]] | None = None,
    operation_logs: list[dict[str, Any]] | None = None,
    fail_operation_log_insert: bool = False,
) -> tuple[Settings, FakePool, FakeRedis, str]:
    """准备操作日志接口测试上下文。

    用途：
        创建测试配置、Fake MySQL、Fake Redis 和可用 JWT，供接口测试复用。
    参数：
        auth_permission_codes：当前用户角色拥有的权限编码。
        users：业务接口测试需要的用户列表。
        roles：业务接口测试需要的角色列表。
        operation_logs：预置操作日志列表。
        fail_operation_log_insert：是否模拟操作日志写入失败。
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
        operation_logs=operation_logs,
        fail_operation_log_insert=fail_operation_log_insert,
    )
    manager = AuthManagement(mysql_pool, redis_client, settings)
    result = await manager.login(LoginRequest(username="admin", password="secret"))
    return settings, mysql_pool, redis_client, result["access_token"]
