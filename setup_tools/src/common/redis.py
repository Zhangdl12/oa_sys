from typing import Protocol

from redis.asyncio import Redis


class RedisSettings(Protocol):
    """Redis 配置协议。

    用途：
        约束创建 Redis 客户端所需配置字段。
    参数：
        无构造参数。
    返回值：
        协议类型本身，仅用于类型检查。
    """

    redis_url: str
    redis_password: str


async def create_redis_client(settings: RedisSettings) -> Redis:
    """创建 Redis 异步客户端。

    用途：
        在应用启动阶段初始化 Redis 客户端，用于登录态、权限缓存和分布式锁。
    参数：
        settings：包含 Redis 连接地址和可选密码的配置对象。
    返回值：
        已完成 ping 校验的 Redis 客户端。
    """

    password = settings.redis_password or None
    client = Redis.from_url(
        settings.redis_url,
        password=password,
        decode_responses=True,
        # 固定 RESP2，避免 redis-py 8 默认 RESP3 发送 HELLO，兼容旧 Redis 服务端。
        protocol=2,
    )
    await client.ping()
    return client


async def close_redis_client(client: Redis | None) -> None:
    """关闭 Redis 异步客户端。

    用途：
        在应用关闭阶段释放 Redis 连接资源。
    参数：
        client：需要关闭的 Redis 客户端，允许为空。
    返回值：
        无返回值。
    """

    if client is None:
        return
    await client.aclose()
