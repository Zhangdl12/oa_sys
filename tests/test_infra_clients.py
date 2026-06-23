import asyncio
from typing import Any

from asyncmy.cursors import DictCursor
from common import mysql as mysql_module
from common import redis as redis_module

from services.oa_admin.core.config import Settings


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


def test_create_mysql_pool_uses_asyncmy_cursor_cls(monkeypatch) -> None:
    """验证 MySQL 连接池使用 asyncmy 支持的字典游标参数。

    用途：
        防止连接池初始化时继续传入 asyncmy.connect 不支持的 cursorclass 参数。
    参数：
        monkeypatch：pytest 提供的运行时替换工具，用于拦截真实数据库连接。
    返回值：
        无返回值。
    """

    captured_kwargs: dict[str, Any] = {}
    fake_pool = object()

    async def fake_create_pool(**kwargs: Any) -> object:
        """记录连接池创建参数并返回假连接池。

        用途：
            替代 asyncmy.create_pool，避免测试连接真实 MySQL。
        参数：
            kwargs：create_mysql_pool 传给 asyncmy.create_pool 的所有关键字参数。
        返回值：
            用于断言的假连接池对象。
        """

        captured_kwargs.update(kwargs)
        return fake_pool

    monkeypatch.setattr(mysql_module.asyncmy, "create_pool", fake_create_pool)

    pool = run_async(mysql_module.create_mysql_pool(Settings()))

    assert pool is fake_pool
    assert captured_kwargs["cursor_cls"] is DictCursor
    assert "cursorclass" not in captured_kwargs


def test_create_redis_client_uses_resp2_protocol(monkeypatch) -> None:
    """验证 Redis 客户端固定使用旧服务端兼容的 RESP2 协议。

    用途：
        防止 redis-py 默认使用 RESP3 握手，导致旧 Redis 服务端报 unknown command HELLO。
    参数：
        monkeypatch：pytest 提供的运行时替换工具，用于拦截真实 Redis 连接。
    返回值：
        无返回值。
    """

    captured_kwargs: dict[str, Any] = {}

    class FakeRedisClient:
        """测试用 Redis 客户端。

        用途：
            模拟 Redis.from_url 返回对象的 ping 行为。
        参数：
            无。
        返回值：
            测试 Redis 客户端实例。
        """

        async def ping(self) -> bool:
            """返回固定 ping 成功结果。

            用途：
                避免测试连接真实 Redis，只验证客户端创建参数。
            参数：
                无。
            返回值：
                固定返回 True。
            """

            return True

    def fake_from_url(url: str, **kwargs: Any) -> FakeRedisClient:
        """记录 Redis 客户端创建参数。

        用途：
            替代 Redis.from_url，捕获 protocol、password 和 decode_responses 等参数。
        参数：
            url：Redis 连接地址。
            kwargs：Redis.from_url 收到的关键字参数。
        返回值：
            FakeRedisClient 实例。
        """

        captured_kwargs["url"] = url
        captured_kwargs.update(kwargs)
        return FakeRedisClient()

    settings = Settings(redis_password="123456")
    monkeypatch.setattr(redis_module.Redis, "from_url", staticmethod(fake_from_url))

    client = run_async(redis_module.create_redis_client(settings))

    assert isinstance(client, FakeRedisClient)
    assert captured_kwargs["url"] == settings.redis_url
    assert captured_kwargs["password"] == "123456"
    assert captured_kwargs["protocol"] == 2
