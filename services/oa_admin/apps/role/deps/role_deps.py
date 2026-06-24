from typing import Annotated, Any

from fastapi import Depends

from services.oa_admin.apps.external.deps.external_deps import get_notification_management
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.role.managements.role_management import RoleManagement
from services.oa_admin.apps.role.managements.role_notification_management import (
    RoleNotificationManagement,
)
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client

MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]
RedisClientDep = Annotated[Any, Depends(get_redis_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
NotificationManagementDep = Annotated[
    NotificationManagement,
    Depends(get_notification_management),
]


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


def get_role_notification_management(
    settings: SettingsDep,
    notification_management: NotificationManagementDep,
) -> RoleNotificationManagement:
    """组装角色通知业务对象。"""

    return RoleNotificationManagement(
        settings=settings,
        notification_management=notification_management,
    )
