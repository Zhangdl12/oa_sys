from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends, Request

from services.oa_admin.apps.auth.deps.auth_deps import permission_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.external.feishu.deps.feishu_deps import (
    get_feishu_management,
    get_notification_management,
    get_notify_log_management,
)
from services.oa_admin.apps.external.feishu.managements.feishu_management import FeishuManagement
from services.oa_admin.apps.external.feishu.managements.notification_management import (
    NotificationManagement,
)
from services.oa_admin.apps.external.feishu.managements.notify_log_management import (
    ExternalNotifyLogManagement,
)
from services.oa_admin.apps.external.feishu.models.feishu import FeishuNotifyRequest
from services.oa_admin.apps.external.feishu.models.notification import (
    CardNotificationRequest,
    TextNotificationRequest,
)
from services.oa_admin.apps.external.feishu.models.notify_log import ExternalNotifyLogListQuery
from services.oa_admin.apps.operation_log.deps.operation_log_deps import operation_log_record

router = APIRouter()


@router.post("/feishu/notify")
async def send_feishu_notify(
    request: Request,
    payload: FeishuNotifyRequest,
    feishu_management: Annotated[FeishuManagement, Depends(get_feishu_management)],
    current_user: Annotated[CurrentUser, Depends(permission_check("external:feishu_notify"))],
    operation_log: Annotated[None, Depends(operation_log_record("发送飞书文本通知"))],
) -> dict:
    request_id = str(getattr(request.state, "request_id", ""))
    data = await feishu_management.send_text_notify(
        payload,
        sender_user_id=current_user.user_id,
        request_id=request_id,
    )
    return success(data)


@router.post("/notify/send-text")
async def send_text_notification(
    request: Request,
    payload: TextNotificationRequest,
    notification_management: Annotated[
        NotificationManagement,
        Depends(get_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("external:feishu_notify"))],
    operation_log: Annotated[None, Depends(operation_log_record("发送模块文本通知"))],
) -> dict:
    request_id = str(getattr(request.state, "request_id", ""))
    data = await notification_management.send_text_notification(
        payload,
        sender_user_id=current_user.user_id,
        request_id=request_id,
    )
    return success(data)


@router.post("/notify/send-card")
async def send_card_notification(
    request: Request,
    payload: CardNotificationRequest,
    notification_management: Annotated[
        NotificationManagement,
        Depends(get_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("external:feishu_notify"))],
    operation_log: Annotated[None, Depends(operation_log_record("发送模块卡片通知"))],
) -> dict:
    request_id = str(getattr(request.state, "request_id", ""))
    data = await notification_management.send_card_notification(
        payload,
        sender_user_id=current_user.user_id,
        request_id=request_id,
    )
    return success(data)


@router.get("/notify-logs")
async def list_external_notify_logs(
    query: Annotated[ExternalNotifyLogListQuery, Depends()],
    notify_log_management: Annotated[
        ExternalNotifyLogManagement,
        Depends(get_notify_log_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("external:notify_log_list"))],
) -> dict:
    data = await notify_log_management.list_notify_logs(query)
    return success(data)
