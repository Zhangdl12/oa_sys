from typing import Protocol

import httpx


class HTTPSettings(Protocol):
    """HTTP 客户端配置协议。

    用途：
        约束创建 httpx.AsyncClient 所需的超时和连接池配置字段。
    参数：
        无构造参数。
    返回值：
        协议类型本身，仅用于类型检查。
    """

    http_timeout_seconds: int
    http_max_connections: int # 连接池大小
    http_max_keepalive_connections: int # 连接池中保持活动的最大连接数


def create_http_client(settings: HTTPSettings) -> httpx.AsyncClient:
    """创建异步 HTTP 客户端。

    用途：
        统一创建外部平台调用使用的 httpx.AsyncClient，避免每次请求重复创建连接。
    参数：
        settings：包含超时和连接池大小的配置对象。
    返回值：
        httpx.AsyncClient 实例。
    """

    timeout = httpx.Timeout(settings.http_timeout_seconds)
    limits = httpx.Limits(
        max_connections=settings.http_max_connections,
        max_keepalive_connections=settings.http_max_keepalive_connections,
    )
    return httpx.AsyncClient(timeout=timeout, limits=limits)


async def close_http_client(client: httpx.AsyncClient | None) -> None:
    """关闭异步 HTTP 客户端。

    用途：
        在应用关闭阶段释放 httpx 连接池资源。
    参数：
        client：需要关闭的 httpx.AsyncClient，允许为空。
    返回值：
        无返回值。
    """

    if client is None:
        return
    await client.aclose()
