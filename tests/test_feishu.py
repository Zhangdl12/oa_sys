import asyncio
import json
from typing import Any

import pytest
from common.exceptions import FeishuException
from common.external.feishu import FeishuClient


def run_async(coro):
    """运行异步测试逻辑。

    用途：
        在不依赖 pytest-asyncio 插件的情况下执行 async/await 测试代码。
    参数：
        coro：需要执行的协程对象。
    返回值：
        协程执行后的返回值。
    """

    return asyncio.run(coro)


class FakeResponse:
    """测试用 HTTP 响应。"""

    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        """模拟 HTTP 状态正常。"""

        return None

    def json(self) -> Any:
        """返回测试响应 JSON。"""

        return self.payload


class FakeHttpClient:
    """测试用 HTTP 客户端。"""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.post_calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """记录 POST 请求并返回测试响应。"""

        self.post_calls.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


class FakeRedis:
    """测试用 Redis 客户端。"""

    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.set_calls: list[dict[str, Any]] = []

    async def get(self, key: str) -> str | None:
        """返回测试缓存。"""

        return self.value

    async def set(self, key: str, value: str, ex: int) -> None:
        """记录缓存写入。"""

        self.set_calls.append({"key": key, "value": value, "ex": ex})
        self.value = value


def test_get_cached_tenant_access_token_uses_cached_token() -> None:
    """Redis 已有 token 时直接返回缓存，不请求飞书。"""

    redis = FakeRedis(json.dumps({"tenant_access_token": "cached-token", "expire": 7200}))
    http_client = FakeHttpClient({"code": 0, "tenant_access_token": "remote-token", "expire": 7200})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    token = run_async(
        client.get_cached_tenant_access_token(
            redis_client=redis,
            app_name="oa_admin",
            app_id="cli_xxx",
            app_secret="secret",
        )
    )

    assert token == "cached-token"
    assert http_client.post_calls == []
    assert redis.set_calls == []


def test_get_cached_tenant_access_token_fetches_and_caches_token() -> None:
    """Redis 未命中时请求飞书，并按 expire 减安全余量写入缓存。"""

    redis = FakeRedis()
    http_client = FakeHttpClient({"code": 0, "tenant_access_token": "remote-token", "expire": 7200})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    token = run_async(
        client.get_cached_tenant_access_token(
            redis_client=redis,
            app_name="oa_admin",
            app_id="cli_xxx",
            app_secret="secret",
        )
    )

    assert token == "remote-token"
    assert http_client.post_calls[0]["url"].endswith(
        "/open-apis/auth/v3/tenant_access_token/internal"
    )
    assert http_client.post_calls[0]["json"] == {
        "app_id": "cli_xxx",
        "app_secret": "secret",
    }
    assert redis.set_calls[0]["key"] == "oa:external:feishu:token:oa_admin"
    assert redis.set_calls[0]["ex"] == 6900
    assert json.loads(redis.set_calls[0]["value"]) == {
        "tenant_access_token": "remote-token",
        "expire": 7200,
    }


def test_get_cached_tenant_access_token_uses_minimum_ttl() -> None:
    """expire 太小时使用最低缓存 TTL。"""

    redis = FakeRedis()
    http_client = FakeHttpClient({"code": 0, "tenant_access_token": "remote-token", "expire": 120})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    token = run_async(
        client.get_cached_tenant_access_token(
            redis_client=redis,
            app_name="oa_admin",
            app_id="cli_xxx",
            app_secret="secret",
        )
    )

    assert token == "remote-token"
    assert redis.set_calls[0]["ex"] == 60


def test_get_tenant_access_token_raises_when_feishu_returns_error() -> None:
    """飞书返回非 0 code 时抛出飞书异常。"""

    http_client = FakeHttpClient({"code": 999, "msg": "bad app"})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    with pytest.raises(FeishuException) as exc_info:
        run_async(client.get_tenant_access_token(app_id="cli_xxx", app_secret="secret"))

    assert exc_info.value.msg == "bad app"


def test_get_tenant_access_token_raises_when_token_missing() -> None:
    """飞书响应缺少 tenant_access_token 时抛出飞书异常。"""

    http_client = FakeHttpClient({"code": 0, "msg": "ok", "expire": 7200})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    with pytest.raises(FeishuException) as exc_info:
        run_async(client.get_tenant_access_token(app_id="cli_xxx", app_secret="secret"))

    assert exc_info.value.msg == "飞书 token 响应缺少 tenant_access_token"


def test_send_text_message_posts_feishu_payload() -> None:
    """发送文本消息时请求 URL、头和 body 符合飞书接口要求。"""

    http_client = FakeHttpClient({"code": 0, "msg": "ok", "data": {"message_id": "om_xxx"}})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    payload = run_async(
        client.send_text_message(
            tenant_access_token="tenant-token",
            receive_id_type="open_id",
            receive_id="ou_xxx",
            text="你好",
        )
    )

    assert payload["code"] == 0
    call = http_client.post_calls[0]
    assert call["url"].endswith("/open-apis/im/v1/messages")
    assert call["params"] == {"receive_id_type": "open_id"}
    assert call["headers"]["Authorization"] == "Bearer tenant-token"
    assert call["json"]["receive_id"] == "ou_xxx"
    assert call["json"]["msg_type"] == "text"
    assert json.loads(call["json"]["content"]) == {"text": "你好"}


def test_send_text_message_supports_chat_id() -> None:
    """发送群消息时请求 query 使用 chat_id。"""

    http_client = FakeHttpClient({"code": 0, "msg": "ok", "data": {"message_id": "om_xxx"}})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    payload = run_async(
        client.send_text_message(
            tenant_access_token="tenant-token",
            receive_id_type="chat_id",
            receive_id="oc_xxx",
            text="群通知测试",
        )
    )

    assert payload["code"] == 0
    call = http_client.post_calls[0]
    assert call["params"] == {"receive_id_type": "chat_id"}
    assert call["json"]["receive_id"] == "oc_xxx"


def test_send_text_message_raises_when_feishu_returns_error() -> None:
    """飞书发送消息返回非 0 code 时抛出飞书异常。"""

    http_client = FakeHttpClient({"code": 999, "msg": "send failed"})
    client = FeishuClient(http_client=http_client, base_url="https://open.feishu.cn")

    with pytest.raises(FeishuException) as exc_info:
        run_async(
            client.send_text_message(
                tenant_access_token="tenant-token",
                receive_id_type="open_id",
                receive_id="ou_xxx",
                text="你好",
            )
        )

    assert exc_info.value.msg == "send failed"
