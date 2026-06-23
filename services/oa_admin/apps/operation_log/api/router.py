from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends, Path

from services.oa_admin.apps.auth.deps.auth_deps import permission_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.operation_log.deps.operation_log_deps import (
    get_operation_log_management,
)
from services.oa_admin.apps.operation_log.managements.operation_log_management import (
    OperationLogManagement,
)
from services.oa_admin.apps.operation_log.models.operation_log import OperationLogListQuery

router = APIRouter()


@router.get("")
async def list_operation_logs(
    query: Annotated[OperationLogListQuery, Depends()],
    operation_log_management: Annotated[
        OperationLogManagement,
        Depends(get_operation_log_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("operation_log:list"))],
) -> dict:
    """查询操作日志列表。

    用途：
        按条件分页查询后台关键操作日志，供审计页面使用。
    参数：
        query：操作日志列表筛选和分页条件。
        operation_log_management：操作日志管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含分页操作日志。
    """

    data = await operation_log_management.list_operation_logs(query)
    return success(data)


@router.get("/{log_id}")
async def get_operation_log(
    log_id: Annotated[int, Path(ge=1)],
    operation_log_management: Annotated[
        OperationLogManagement,
        Depends(get_operation_log_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("operation_log:list"))],
) -> dict:
    """查询操作日志详情。

    用途：
        按操作日志 ID 查询单条日志详情。
    参数：
        log_id：操作日志 ID。
        operation_log_management：操作日志管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含操作日志详情。
    """

    data = await operation_log_management.get_operation_log(log_id)
    return success(data)
