from typing import Any

from common.exceptions import BusinessException
from fastapi import Request


def get_mysql_pool(request: Request) -> Any:
    """获取 MySQL 连接池。

    用途：
        供 deps 层从 FastAPI 请求上下文中读取全局 MySQL 连接池。
    参数：
        request：当前 HTTP 请求对象。
    返回值：
        MySQL 异步连接池对象。
    """

    pool = getattr(request.app.state, "mysql_pool", None)
    if pool is None:
        raise BusinessException(code=50000, msg="MySQL连接池未初始化")
    return pool
