from typing import Annotated, Any

from fastapi import Depends

from services.oa_admin.apps.role.managements.role_management import RoleManagement
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client

MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]
RedisClientDep = Annotated[Any, Depends(get_redis_client)]


def get_role_management(
    mysql_pool: MySQLPoolDep,
    redis_client: RedisClientDep,
) -> RoleManagement:
    """组装角色管理业务对象。

    用途：
        从 FastAPI 依赖中注入 MySQL 和 Redis，并创建 RoleManagement。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
    返回值：
        RoleManagement 实例。
    """

    return RoleManagement(mysql_pool=mysql_pool, redis_client=redis_client)
