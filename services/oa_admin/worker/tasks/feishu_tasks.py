import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from common.http import close_http_client, create_http_client
from common.mysql import close_mysql_pool, create_mysql_pool
from common.redis import close_redis_client, create_redis_client

from services.oa_admin.apps.external.feishu.managements.feishu_management import (
    FeishuManagement,
)
from services.oa_admin.apps.external.feishu.models.feishu import FeishuCardNotifyRequest
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.worker.celery_app import celery_app

TASK_NAME = "send_hourly_feishu_card_notify"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@celery_app.task(name=TASK_NAME)
def send_hourly_feishu_card_notify() -> dict[str, Any]:
    """每小时飞书卡片通知的 Celery 任务入口。"""

    return asyncio.run(send_hourly_feishu_card_notify_async())


async def send_hourly_feishu_card_notify_async(
    settings: Settings | None = None,
    feishu_management: FeishuManagement | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """发送一次每小时飞书卡片通知。

    可选依赖用于测试时注入桩对象，避免创建真实 HTTP、Redis 和 MySQL 连接。
    """

    current_settings = settings or get_settings()
    if not current_settings.feishu_hourly_notify_enabled:
        return {"status": "skipped", "reason": "disabled"}
    receive_id = current_settings.feishu_hourly_notify_user_id.strip()
    if not receive_id:
        return {"status": "skipped", "reason": "missing_user_id"}

    current_time = now or datetime.now(BEIJING_TZ)
    request_id = _build_request_id(current_time)
    payload = FeishuCardNotifyRequest(
        receive_id_type="user_id",
        receive_id=receive_id,
        card=_build_hourly_card(current_time),
        content_summary=f"OA 每小时定时通知 {current_time.strftime('%Y-%m-%d %H:%S')}",
    )

    if feishu_management is not None:
        result = await feishu_management.send_card_notify(
            payload,
            sender_user_id=None,
            request_id=request_id,
        )
        return {"status": "sent", "request_id": request_id, "result": result}

    result = await _send_with_resources(current_settings, payload, request_id)
    return {"status": "sent", "request_id": request_id, "result": result}


async def _send_with_resources(
    settings: Settings,
    payload: FeishuCardNotifyRequest,
    request_id: str,
) -> dict[str, Any]:
    """创建任务内资源，发送卡片，并在结束后释放资源。"""

    http_client = create_http_client(settings)
    redis_client = None
    mysql_pool = None
    try:
        redis_client = await create_redis_client(settings)
        mysql_pool = await create_mysql_pool(settings)
        feishu_management = FeishuManagement(
            http_client=http_client,
            redis_client=redis_client,
            mysql_pool=mysql_pool,
            settings=settings,
        )
        return await feishu_management.send_card_notify(
            payload,
            sender_user_id=None,
            request_id=request_id,
        )
    finally:
        await close_mysql_pool(mysql_pool)
        await close_redis_client(redis_client)
        await close_http_client(http_client)


def _build_hourly_card(now: datetime) -> dict[str, Any]:
    """构造每小时通知使用的飞书交互卡片。"""

    display_time = now.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"时间：{display_time}\n"
                        "来源：Celery Beat\n"
                        "说明：OA 后台每小时定时通知。"
                    ),
                    "text_align": "left",
                    "text_size": "normal",
                    "margin": "0px 0px 0px 0px",
                    "element_id": "hourly_feishu_notify_detail",
                }
            ],
        },
        "header": {
            "title": {"tag": "plain_text", "content": "OA 每小时定时通知"},
            "subtitle": {"tag": "plain_text", "content": ""},
            "template": "blue",
            "icon": {"tag": "standard_icon", "token": "time_outlined"},
            "padding": "12px 8px 12px 8px",
        },
    }


def _build_request_id(now: datetime) -> str:
    """生成按小时稳定的 request_id，便于通知日志追踪。"""

    return f"celery-hourly-feishu-{now.astimezone(BEIJING_TZ).strftime('%Y%m%d%H')}"
