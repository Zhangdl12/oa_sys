from typing import Any

from common.exceptions import BusinessException
from fastapi import Request


def get_redis_client(request: Request) -> Any:
    """获取 Redis 客户端。

    用途：
        供 deps 层从 FastAPI 请求上下文中读取全局 Redis 客户端。
    参数：
        request：当前 HTTP 请求对象。
    返回值：
        Redis 异步客户端对象。
    """

    client = getattr(request.app.state, "redis_client", None)
    if client is None:
        raise BusinessException(code=50000, msg="Redis客户端未初始化")
    return client
