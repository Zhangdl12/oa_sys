import asyncio
import json
from datetime import datetime
from typing import Any

import pytest
from common.exceptions import BusinessException, FeishuException
from fastapi.testclient import TestClient

from services.oa_admin.apps.auth.constants import RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.deps.auth_deps import login_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.external.feishu.deps.feishu_deps import (
    get_feishu_management,
    get_notification_management,
)
from services.oa_admin.apps.external.feishu.managements.feishu_management import FeishuManagement
from services.oa_admin.apps.external.feishu.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.feishu.managements.notify_log_management import (
    ExternalNotifyLogManagement,
)
from services.oa_admin.apps.external.feishu.models.feishu import (
    FeishuCardNotifyRequest,
    FeishuNotifyRequest,
)
from services.oa_admin.apps.external.feishu.models.notification import (
    CardNotificationRequest,
    TextNotificationRequest,
)
from services.oa_admin.apps.external.feishu.models.notify_log import ExternalNotifyLogListQuery
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client
from services.oa_admin.main import app


def run_async(coro):
    return asyncio.run(coro)


class FakeFeishuClient:
    def __init__(self, send_error: Exception | None = None) -> None:
        self.send_error = send_error
        self.token_calls: list[dict[str, Any]] = []
        self.message_calls: list[dict[str, Any]] = []
        self.card_calls: list[dict[str, Any]] = []

    async def get_cached_tenant_access_token(
        self,
        redis_client: Any,
        app_name: str,
        app_id: str,
        app_secret: str,
    ) -> str:
        self.token_calls.append(
            {
                "redis_client": redis_client,
                "app_name": app_name,
                "app_id": app_id,
                "app_secret": app_secret,
            }
        )
        return "tenant-token"

    async def send_text_message(
        self,
        tenant_access_token: str,
        receive_id_type: str,
        receive_id: str,
        text: str,
    ) -> dict[str, Any]:
        if self.send_error is not None:
            raise self.send_error
        self.message_calls.append(
            {
                "tenant_access_token": tenant_access_token,
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "text": text,
            }
        )
        return {"code": 0, "msg": "ok", "data": {"message_id": "om_xxx"}}

    async def send_card_message(
        self,
        tenant_access_token: str,
        receive_id_type: str,
        receive_id: str,
        card: dict[str, Any],
    ) -> dict[str, Any]:
        if self.send_error is not None:
            raise self.send_error
        self.card_calls.append(
            {
                "tenant_access_token": tenant_access_token,
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "card": card,
            }
        )
        return {"code": 0, "msg": "ok", "data": {"message_id": "om_card"}}


class FakeRedis:
    def __init__(self, permissions: list[str] | None = None) -> None:
        self.values = {
            RBAC_USER_KEY_TEMPLATE.format(user_id=1): json.dumps(
                {
                    "role_id": 1,
                    "permissions": (
                        ["external:feishu_notify"] if permissions is None else permissions
                    ),
                }
            )
        }

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


class FakeCursor:
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
        self.sql = sql
        self.params = params
        if "INSERT INTO sys_external_notify_log" in sql:
            log_id = self.pool.next_notify_log_id
            self.pool.next_notify_log_id += 1
            self.lastrowid = log_id
            self.pool.notify_logs_by_id[log_id] = build_notify_log(
                log_id=log_id,
                platform=str(params[0]),
                notify_type=str(params[1]),
                receive_id_type=str(params[2]),
                receive_id=str(params[3]),
                content_summary=str(params[4]),
                sender_user_id=params[5],
                request_id=str(params[6]),
                result=str(params[7]),
                external_message_id=str(params[8]),
                error_msg=str(params[9]),
            )

    async def fetchone(self) -> dict[str, Any] | None:
        if "COUNT(*) AS total" in self.sql:
            return {"total": len(self.pool.notify_logs_by_id)}
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        if "FROM sys_external_notify_log" in self.sql:
            logs = sorted(
                self.pool.notify_logs_by_id.values(),
                key=lambda item: int(item["id"]),
                reverse=True,
            )
            limit = int(self.params[-2])
            offset = int(self.params[-1])
            return logs[offset : offset + limit]
        return []


class FakeConnection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.pool)

    async def commit(self) -> None:
        return None


class FakePool:
    def __init__(self, notify_logs: list[dict[str, Any]] | None = None) -> None:
        self.notify_logs_by_id = {int(item["id"]): item for item in notify_logs or []}
        self.next_notify_log_id = max(self.notify_logs_by_id.keys(), default=0) + 1

    def acquire(self) -> FakeConnection:
        return FakeConnection(self)


class StubFeishuManagement:
    def __init__(self) -> None:
        self.payloads: list[FeishuNotifyRequest] = []
        self.card_payloads: list[FeishuCardNotifyRequest] = []
        self.sender_user_ids: list[int | None] = []
        self.request_ids: list[str] = []

    async def send_text_notify(
        self,
        payload: FeishuNotifyRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        return {"message_id": "om_xxx"}

    async def send_card_notify(
        self,
        payload: FeishuCardNotifyRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.card_payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        return {"message_id": "om_card"}


class StubNotificationManagement:
    def __init__(self) -> None:
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
        return {"message_id": "om_xxx"}

    async def send_card_notification(
        self,
        payload: CardNotificationRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.card_payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        return {"message_id": "om_card"}


def build_notify_log(
    log_id: int = 1,
    platform: str = "feishu",
    notify_type: str = "text",
    receive_id_type: str = "open_id",
    receive_id: str = "ou_xxx",
    content_summary: str = "hello",
    sender_user_id: int | None = 1,
    request_id: str = "req-1",
    result: str = "success",
    external_message_id: str = "om_xxx",
    error_msg: str = "",
) -> dict[str, Any]:
    return {
        "id": log_id,
        "platform": platform,
        "notify_type": notify_type,
        "receive_id_type": receive_id_type,
        "receive_id": receive_id,
        "content_summary": content_summary,
        "sender_user_id": sender_user_id,
        "request_id": request_id,
        "result": result,
        "external_message_id": external_message_id,
        "error_msg": error_msg,
        "created_at": datetime(2026, 6, 22, 12, 0, 0),
    }


def current_user_override() -> CurrentUser:
    return CurrentUser(
        user_id=1,
        username="admin",
        real_name="管理员",
        role_id=1,
        token_version=1,
        jti="test-jti",
    )


def test_feishu_management_rejects_disabled_config() -> None:
    pool = FakePool()
    manager = FeishuManagement(
        http_client=object(),
        redis_client=object(),
        mysql_pool=pool,
        settings=Settings(feishu_enabled=False),
    )

    with pytest.raises(BusinessException) as exc_info:
        run_async(
            manager.send_text_notify(
                FeishuNotifyRequest(receive_id="ou_xxx", text="你好"),
                sender_user_id=1,
                request_id="req-1",
            )
        )

    assert exc_info.value.msg == "飞书集成未启用"
    log = pool.notify_logs_by_id[1]
    assert log["result"] == "failed"
    assert log["error_msg"] == "飞书集成未启用"


def test_feishu_management_sends_text_notify_and_writes_success_log() -> None:
    pool = FakePool()
    manager = FeishuManagement(
        http_client=object(),
        redis_client=object(),
        mysql_pool=pool,
        settings=Settings(
            feishu_enabled=True,
            feishu_app_id="cli_xxx",
            feishu_app_secret="secret",
        ),
    )
    fake_client = FakeFeishuClient()
    manager.client = fake_client

    result = run_async(
        manager.send_text_notify(
            FeishuNotifyRequest(receive_id="ou_xxx", text="你好"),
            sender_user_id=1,
            request_id="req-1",
        )
    )

    assert result["data"]["message_id"] == "om_xxx"
    assert fake_client.token_calls[0]["app_name"] == "oa_admin"
    assert fake_client.message_calls[0] == {
        "tenant_access_token": "tenant-token",
        "receive_id_type": "open_id",
        "receive_id": "ou_xxx",
        "text": "你好",
    }
    log = pool.notify_logs_by_id[1]
    assert log["result"] == "success"
    assert log["external_message_id"] == "om_xxx"
    assert log["content_summary"] == "你好"


def test_feishu_management_sends_card_notify_and_writes_success_log() -> None:
    pool = FakePool()
    manager = FeishuManagement(
        http_client=object(),
        redis_client=object(),
        mysql_pool=pool,
        settings=Settings(
            feishu_enabled=True,
            feishu_app_id="cli_xxx",
            feishu_app_secret="secret",
        ),
    )
    fake_client = FakeFeishuClient()
    manager.client = fake_client
    card = {"schema": "2.0", "header": {"title": {"content": "用户创建成功"}}}

    result = run_async(
        manager.send_card_notify(
            FeishuCardNotifyRequest(
                receive_id_type="chat_id",
                receive_id="oc_xxx",
                card=card,
                content_summary="用户 staff 创建成功",
            ),
            sender_user_id=1,
            request_id="req-1",
        )
    )

    assert result["data"]["message_id"] == "om_card"
    assert fake_client.card_calls[0] == {
        "tenant_access_token": "tenant-token",
        "receive_id_type": "chat_id",
        "receive_id": "oc_xxx",
        "card": card,
    }
    log = pool.notify_logs_by_id[1]
    assert log["notify_type"] == "card"
    assert log["result"] == "success"
    assert log["external_message_id"] == "om_card"
    assert log["content_summary"] == "用户 staff 创建成功"


def test_feishu_management_writes_failed_log_when_send_fails() -> None:
    pool = FakePool()
    manager = FeishuManagement(
        http_client=object(),
        redis_client=object(),
        mysql_pool=pool,
        settings=Settings(
            feishu_enabled=True,
            feishu_app_id="cli_xxx",
            feishu_app_secret="secret",
        ),
    )
    manager.client = FakeFeishuClient(send_error=FeishuException(msg="send failed"))

    with pytest.raises(FeishuException):
        run_async(
            manager.send_text_notify(
                FeishuNotifyRequest(receive_id="ou_xxx", text="你好"),
                sender_user_id=1,
                request_id="req-1",
            )
        )

    log = pool.notify_logs_by_id[1]
    assert log["result"] == "failed"
    assert log["error_msg"] == "send failed"


def test_feishu_management_writes_failed_log_when_card_send_fails() -> None:
    pool = FakePool()
    manager = FeishuManagement(
        http_client=object(),
        redis_client=object(),
        mysql_pool=pool,
        settings=Settings(
            feishu_enabled=True,
            feishu_app_id="cli_xxx",
            feishu_app_secret="secret",
        ),
    )
    manager.client = FakeFeishuClient(send_error=FeishuException(msg="send failed"))

    with pytest.raises(FeishuException):
        run_async(
            manager.send_card_notify(
                FeishuCardNotifyRequest(
                    receive_id="ou_xxx",
                    card={"schema": "2.0"},
                    content_summary="用户 staff 创建成功",
                ),
                sender_user_id=1,
                request_id="req-1",
            )
        )

    log = pool.notify_logs_by_id[1]
    assert log["notify_type"] == "card"
    assert log["result"] == "failed"
    assert log["error_msg"] == "send failed"


def test_notify_log_management_lists_logs() -> None:
    manager = ExternalNotifyLogManagement(
        FakePool(
            notify_logs=[
                build_notify_log(log_id=1, result="failed"),
                build_notify_log(log_id=2, result="success"),
            ]
        )
    )

    result = run_async(
        manager.list_notify_logs(ExternalNotifyLogListQuery(page=1, page_size=1))
    )

    assert result["total"] == 2
    assert result["page"] == 1
    assert result["page_size"] == 1
    assert result["items"][0]["id"] == 2


def test_notification_management_converts_payload_to_feishu_text() -> None:
    feishu_management = StubFeishuManagement()
    manager = NotificationManagement(feishu_management)

    result = run_async(
        manager.send_text_notification(
            TextNotificationRequest(
                receive_id="ou_xxx",
                title="系统通知",
                content="测试飞书文本消息",
                operator="admin",
            ),
            sender_user_id=1,
            request_id="req-1",
        )
    )

    assert result == {"message_id": "om_xxx"}
    assert feishu_management.payloads[0] == FeishuNotifyRequest(
        receive_id_type="open_id",
        receive_id="ou_xxx",
        text="【系统通知】测试飞书文本消息\n操作人：admin",
    )
    assert feishu_management.sender_user_ids[0] == 1
    assert feishu_management.request_ids[0] == "req-1"


def test_notification_management_omits_empty_operator() -> None:
    feishu_management = StubFeishuManagement()
    manager = NotificationManagement(feishu_management)

    run_async(
        manager.send_text_notification(
            TextNotificationRequest(
                receive_id="ou_xxx",
                title="系统通知",
                content="测试飞书文本消息",
            ),
            sender_user_id=1,
            request_id="req-1",
        )
    )

    assert feishu_management.payloads[0].text == "【系统通知】测试飞书文本消息"


def test_notification_management_converts_payload_to_feishu_card() -> None:
    feishu_management = StubFeishuManagement()
    manager = NotificationManagement(feishu_management)
    card = {"schema": "2.0", "header": {"title": {"content": "用户创建成功"}}}

    result = run_async(
        manager.send_card_notification(
            CardNotificationRequest(
                receive_id_type="chat_id",
                receive_id="oc_xxx",
                card=card,
                content_summary="用户 staff 创建成功",
            ),
            sender_user_id=1,
            request_id="req-1",
        )
    )

    assert result == {"message_id": "om_card"}
    assert feishu_management.card_payloads[0] == FeishuCardNotifyRequest(
        receive_id_type="chat_id",
        receive_id="oc_xxx",
        card=card,
        content_summary="用户 staff 创建成功",
    )
    assert feishu_management.sender_user_ids[0] == 1
    assert feishu_management.request_ids[0] == "req-1"


def test_feishu_notify_api_calls_management() -> None:
    manager = StubFeishuManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()

    app.dependency_overrides[get_feishu_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/feishu/notify",
                json={"receive_id": "ou_xxx", "text": "你好"},
                headers={"Authorization": "Bearer test-token", "X-Request-ID": "req-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {"message_id": "om_xxx"}
    assert manager.payloads[0].receive_id_type == "open_id"
    assert manager.payloads[0].receive_id == "ou_xxx"
    assert manager.payloads[0].text == "你好"
    assert manager.sender_user_ids[0] == 1
    assert manager.request_ids[0] == "req-1"


def test_send_text_notification_api_calls_management() -> None:
    manager = StubNotificationManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()

    app.dependency_overrides[get_notification_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/notify/send-text",
                json={
                    "receive_id_type": "open_id",
                    "receive_id": "ou_xxx",
                    "title": "系统通知",
                    "content": "测试飞书文本消息",
                    "operator": "admin",
                },
                headers={"Authorization": "Bearer test-token", "X-Request-ID": "req-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {"message_id": "om_xxx"}
    assert manager.payloads[0].title == "系统通知"
    assert manager.payloads[0].content == "测试飞书文本消息"
    assert manager.payloads[0].operator == "admin"
    assert manager.sender_user_ids[0] == 1
    assert manager.request_ids[0] == "req-1"


def test_send_card_notification_api_calls_management() -> None:
    manager = StubNotificationManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()
    card = {
        "schema": "2.0",
        "header": {"title": {"tag": "plain_text", "content": "卡片消息接口测试"}},
    }

    app.dependency_overrides[get_notification_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/notify/send-card",
                json={
                    "receive_id_type": "user_id",
                    "receive_id": "d93addgc",
                    "card": card,
                    "content_summary": "卡片消息接口测试",
                },
                headers={"Authorization": "Bearer test-token", "X-Request-ID": "req-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {"message_id": "om_card"}
    assert manager.card_payloads[0] == CardNotificationRequest(
        receive_id_type="user_id",
        receive_id="d93addgc",
        card=card,
        content_summary="卡片消息接口测试",
    )
    assert manager.sender_user_ids[0] == 1
    assert manager.request_ids[0] == "req-1"


def test_send_text_notification_api_rejects_user_without_permission() -> None:
    manager = StubNotificationManagement()
    redis_client = FakeRedis([])
    mysql_pool = FakePool()
    settings = Settings()

    app.dependency_overrides[get_notification_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/notify/send-text",
                json={
                    "receive_id_type": "open_id",
                    "receive_id": "ou_xxx",
                    "title": "系统通知",
                    "content": "测试飞书文本消息",
                },
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert manager.payloads == []


def test_feishu_notify_api_accepts_chat_id() -> None:
    manager = StubFeishuManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()

    app.dependency_overrides[get_feishu_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/feishu/notify",
                json={
                    "receive_id_type": "chat_id",
                    "receive_id": "oc_xxx",
                    "text": "群通知测试",
                },
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert manager.payloads[0].receive_id_type == "chat_id"
    assert manager.payloads[0].receive_id == "oc_xxx"


def test_feishu_notify_api_accepts_user_id() -> None:
    manager = StubFeishuManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()

    app.dependency_overrides[get_feishu_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/feishu/notify",
                json={
                    "receive_id_type": "user_id",
                    "receive_id": "d93addgc",
                    "text": "用户通知测试",
                },
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert manager.payloads[0].receive_id_type == "user_id"
    assert manager.payloads[0].receive_id == "d93addgc"


def test_feishu_notify_api_rejects_invalid_receive_id_type() -> None:
    manager = StubFeishuManagement()
    redis_client = FakeRedis()
    mysql_pool = FakePool()
    settings = Settings()
    app.dependency_overrides[get_feishu_management] = lambda: manager
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/external/feishu/notify",
                json={
                    "receive_id_type": "email",
                    "receive_id": "a@example.com",
                    "text": "不支持",
                },
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40000


def test_notify_log_list_api_allows_user_with_permission() -> None:
    redis_client = FakeRedis(["external:notify_log_list"])
    mysql_pool = FakePool(notify_logs=[build_notify_log(log_id=1)])
    settings = Settings()
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/external/notify-logs",
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["total"] == 1


def test_notify_log_list_api_rejects_user_without_permission() -> None:
    redis_client = FakeRedis([])
    mysql_pool = FakePool(notify_logs=[build_notify_log(log_id=1)])
    settings = Settings()
    app.dependency_overrides[login_check] = current_user_override
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_mysql_pool] = lambda: mysql_pool
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/external/notify-logs",
                headers={"Authorization": "Bearer test-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
