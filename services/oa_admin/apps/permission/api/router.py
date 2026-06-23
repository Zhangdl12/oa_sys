from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends, Path, Request

from services.oa_admin.apps.auth.deps.auth_deps import permission_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.operation_log.deps.operation_log_deps import operation_log_record
from services.oa_admin.apps.permission.deps.permission_deps import (
    get_permission_management,
    get_permission_notification_management,
)
from services.oa_admin.apps.permission.managements.permission_management import PermissionManagement
from services.oa_admin.apps.permission.managements.permission_notification_management import (
    PermissionNotificationManagement,
)
from services.oa_admin.apps.permission.models.permission import (
    PermissionCreateRequest,
    PermissionListQuery,
    PermissionUpdateRequest,
)

router = APIRouter()


@router.get("")
async def list_permissions(
    query: Annotated[PermissionListQuery, Depends()],
    permission_management: Annotated[PermissionManagement, Depends(get_permission_management)],
    current_user: Annotated[CurrentUser, Depends(permission_check("permission:list"))],
) -> dict:
    """查询权限点列表。

    用途：
        查询系统权限点，供后续角色分配权限和管理后台展示使用。
    参数：
        query：权限列表筛选条件。
        permission_management：权限点管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含权限点列表。
    """

    data = await permission_management.list_permissions(query)
    return success(data)


@router.post("")
async def create_permission(
    payload: PermissionCreateRequest,
    request: Request,
    permission_management: Annotated[PermissionManagement, Depends(get_permission_management)],
    permission_notification_management: Annotated[
        PermissionNotificationManagement,
        Depends(get_permission_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("permission:create"))],
    operation_log: Annotated[None, Depends(operation_log_record("创建权限点"))],
) -> dict:
    """创建权限点。

    用途：
        新增系统权限点，创建后可在角色模块中分配给角色。
    参数：
        payload：创建权限点请求参数。
        request：FastAPI 请求对象，用于读取 request_id。
        permission_management：权限点管理业务对象，由 deps 层组装。
        permission_notification_management：权限点通知业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制和通知操作人。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含创建后的权限点。
    """

    data = await permission_management.create_permission(payload)
    await permission_notification_management.send_permission_create_notification(
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)


@router.put("/{permission_id}")
async def update_permission(
    permission_id: Annotated[int, Path(ge=1)],
    payload: PermissionUpdateRequest,
    request: Request,
    permission_management: Annotated[PermissionManagement, Depends(get_permission_management)],
    permission_notification_management: Annotated[
        PermissionNotificationManagement,
        Depends(get_permission_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("permission:update"))],
    operation_log: Annotated[None, Depends(operation_log_record("更新权限点"))],
) -> dict:
    """更新权限点。

    用途：
        更新权限点名称、类型、父级、路径、方法、状态和排序，不允许修改权限编码。
    参数：
        permission_id：权限点 ID。
        payload：更新权限点请求参数。
        request：FastAPI 请求对象，用于读取 request_id。
        permission_management：权限点管理业务对象，由 deps 层组装。
        permission_notification_management：权限点通知业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制和通知操作人。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含更新后的权限点。
    """

    before_data = await permission_management.get_permission(permission_id)
    data = await permission_management.update_permission(permission_id, payload)
    await permission_notification_management.send_permission_update_notification(
        before_data=before_data,
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)
