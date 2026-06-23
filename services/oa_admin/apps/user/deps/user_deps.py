from typing import Annotated, Any

from fastapi import Depends

from services.oa_admin.apps.external.deps.external_deps import get_notification_management
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.user.managements.user_management import UserManagement
from services.oa_admin.apps.user.managements.user_notification_management import (
    UserNotificationManagement,
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


def get_user_management(
    mysql_pool: MySQLPoolDep,
    redis_client: RedisClientDep,
) -> UserManagement:
    """组装用户管理业务对象。

    用途：
        从 FastAPI 依赖中注入 MySQL 和 Redis，并创建 UserManagement。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
    返回值：
        UserManagement 实例。
    """

    return UserManagement(mysql_pool=mysql_pool, redis_client=redis_client)


def get_user_notification_management(
    settings: SettingsDep,
    notification_management: NotificationManagementDep,
) -> UserNotificationManagement:
    """组装用户通知业务对象。

    用途：
        从 FastAPI 依赖中注入配置和统一通知业务对象，并创建 UserNotificationManagement。
    参数：
        settings：系统配置对象。
        notification_management：统一通知业务对象，由 external deps 层组装。
    返回值：
        UserNotificationManagement 实例。
    """

    return UserNotificationManagement(
        settings=settings,
        notification_management=notification_management,
    )
