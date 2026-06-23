from typing import Annotated, Any

from fastapi import Depends, Request

from services.oa_admin.apps.external.managements.feishu_management import FeishuManagement
from services.oa_admin.apps.external.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.managements.notify_log_management import (
    ExternalNotifyLogManagement,
)
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client

RedisClientDep = Annotated[Any, Depends(get_redis_client)]
MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(request: Request) -> Any:
    """获取 HTTP 客户端。

    用途：
        从 FastAPI app.state 读取全局 httpx.AsyncClient，供外部平台调用复用连接池。
    参数：
        request：当前 HTTP 请求对象。
    返回值：
        HTTP 异步客户端。
    """

    return request.app.state.http_client


HTTPClientDep = Annotated[Any, Depends(get_http_client)]


def get_feishu_management(
    http_client: HTTPClientDep,
    redis_client: RedisClientDep,
    mysql_pool: MySQLPoolDep,
    settings: SettingsDep,
) -> FeishuManagement:
    """组装飞书集成业务对象。

    用途：
        从 FastAPI 依赖中注入 HTTP、Redis 和配置对象，并创建 FeishuManagement。
    参数：
        http_client：HTTP 异步客户端。
        redis_client：Redis 异步客户端。
        settings：应用配置对象。
    返回值：
        FeishuManagement 实例。
    """

    return FeishuManagement(
        http_client=http_client,
        redis_client=redis_client,
        mysql_pool=mysql_pool,
        settings=settings,
    )


def get_notify_log_management(mysql_pool: MySQLPoolDep) -> ExternalNotifyLogManagement:
    """组装外部通知记录查询业务对象。"""

    return ExternalNotifyLogManagement(mysql_pool)


def get_notification_management(
    feishu_management: Annotated[FeishuManagement, Depends(get_feishu_management)],
) -> NotificationManagement:
    """组装统一通知业务对象。"""

    return NotificationManagement(feishu_management)
