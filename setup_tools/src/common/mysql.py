from typing import Protocol

import asyncmy
from asyncmy.cursors import DictCursor
from asyncmy.pool import Pool


class MySQLSettings(Protocol):
    """MySQL 配置协议。

    用途：
        约束创建连接池所需配置，避免公共包直接依赖子应用 Settings 类。
    参数：
        无构造参数。
    返回值：
        协议类型本身，仅用于类型检查。
    """

    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_min_size: int
    mysql_max_size: int


async def create_mysql_pool(settings: MySQLSettings) -> Pool:
    """创建 MySQL 异步连接池。

    用途：
        在应用启动阶段统一初始化 MySQL 连接池，后续通过 app.state 复用。
    参数：
        settings：包含 MySQL 主机、端口、账号、密码、库名和连接池大小的配置对象。
    返回值：
        asyncmy 连接池对象。
    """

    return await asyncmy.create_pool(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        minsize=settings.mysql_min_size,
        maxsize=settings.mysql_max_size,
        # 自动提交业务写入，避免连接释放后事务长期挂起。
        autocommit=True,
        # asyncmy 当前使用 cursor_cls 指定默认游标，不能传 PyMySQL 风格的 cursorclass。
        cursor_cls=DictCursor,
        charset="utf8mb4",
    )


async def close_mysql_pool(pool: Pool | None) -> None:
    """关闭 MySQL 异步连接池。

    用途：
        在应用关闭阶段释放 MySQL 连接池资源。
    参数：
        pool：需要关闭的连接池对象，允许为空。
    返回值：
        无返回值。
    """

    if pool is None:
        return
    # 先标记连接池关闭，再等待已借出的连接归还并释放。
    pool.close()
    await pool.wait_closed()
