from typing import Annotated, Any

from fastapi import Depends, Request

from services.oa_admin.apps.external.feishu.managements.feishu_management import FeishuManagement
from services.oa_admin.apps.external.feishu.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.feishu.managements.notify_log_management import (
    ExternalNotifyLogManagement,
)
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client

RedisClientDep = Annotated[Any, Depends(get_redis_client)]
MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(request: Request) -> Any:
    return request.app.state.http_client


HTTPClientDep = Annotated[Any, Depends(get_http_client)]


def get_feishu_management(
    http_client: HTTPClientDep,
    redis_client: RedisClientDep,
    mysql_pool: MySQLPoolDep,
    settings: SettingsDep,
) -> FeishuManagement:
    return FeishuManagement(
        http_client=http_client,
        redis_client=redis_client,
        mysql_pool=mysql_pool,
        settings=settings,
    )


def get_notification_management(
    feishu_management: Annotated[FeishuManagement, Depends(get_feishu_management)],
) -> NotificationManagement:
    return NotificationManagement(feishu_management)


def get_notify_log_management(mysql_pool: MySQLPoolDep) -> ExternalNotifyLogManagement:
    return ExternalNotifyLogManagement(mysql_pool)
