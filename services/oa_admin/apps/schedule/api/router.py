from typing import Annotated

from common.exceptions import BusinessException
from common.response import success
from fastapi import APIRouter, Depends, Header

from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.worker.tasks.feishu_tasks import TASK_NAME, send_hourly_feishu_card_notify

router = APIRouter()


@router.post("/feishu-hourly-notify/trigger")
async def trigger_feishu_hourly_notify(
    settings: Annotated[Settings, Depends(get_settings)],
    x_schedule_trigger_token: Annotated[str | None, Header()] = None,
) -> dict:
    if not settings.schedule_trigger_token:
        raise BusinessException(code=40300, msg="调度触发令牌未配置")
    if x_schedule_trigger_token != settings.schedule_trigger_token:
        raise BusinessException(code=40300, msg="调度触发令牌无效")

    result = send_hourly_feishu_card_notify.apply_async()
    return success(
        {
            "status": "queued",
            "task_name": TASK_NAME,
            "task_id": result.id,
        }
    )
