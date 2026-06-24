from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends, Path, Request

from services.oa_admin.apps.auth.deps.auth_deps import permission_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.operation_log.deps.operation_log_deps import operation_log_record
from services.oa_admin.apps.role.deps.role_deps import (
    get_role_management,
    get_role_notification_management,
)
from services.oa_admin.apps.role.managements.role_management import RoleManagement
from services.oa_admin.apps.role.managements.role_notification_management import (
    RoleNotificationManagement,
)
from services.oa_admin.apps.role.models.role import (
    RoleAssignPermissionRequest,
    RoleCreateRequest,
    RoleListQuery,
    RoleUpdateRequest,
)

router = APIRouter()


@router.get("")
async def list_roles(
    query: Annotated[RoleListQuery, Depends()],
    role_management: Annotated[RoleManagement, Depends(get_role_management)],
    current_user: Annotated[CurrentUser, Depends(permission_check("role:list"))],
) -> dict:
    """查询角色列表。

    用途：
        查询系统角色，供用户分配角色和管理后台展示使用。
    参数：
        query：角色列表筛选条件。
        role_management：角色管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含角色列表。
    """

    data = await role_management.list_roles(query)
    return success(data)


@router.post("")
async def create_role(
    payload: RoleCreateRequest,
    request: Request,
    role_management: Annotated[RoleManagement, Depends(get_role_management)],
    role_notification_management: Annotated[
        RoleNotificationManagement,
        Depends(get_role_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("role:create"))],
    operation_log: Annotated[None, Depends(operation_log_record("创建角色"))],
) -> dict:
    """创建角色。

    用途：
        新增系统角色，创建后可通过角色分配权限接口绑定权限点。
    参数：
        payload：创建角色请求参数。
        role_management：角色管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含创建后的角色。
    """

    data = await role_management.create_role(payload)
    await role_notification_management.send_role_create_notification(
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)


@router.put("/{role_id}")
async def update_role(
    role_id: Annotated[int, Path(ge=1)],
    payload: RoleUpdateRequest,
    request: Request,
    role_management: Annotated[RoleManagement, Depends(get_role_management)],
    role_notification_management: Annotated[
        RoleNotificationManagement,
        Depends(get_role_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("role:update"))],
    operation_log: Annotated[None, Depends(operation_log_record("更新角色"))],
) -> dict:
    """更新角色。

    用途：
        更新角色名称、状态和备注，不允许修改角色编码。
    参数：
        role_id：角色 ID。
        payload：更新角色请求参数。
        role_management：角色管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含更新后的角色。
    """

    before_data = await role_management.get_role(role_id)
    data = await role_management.update_role(role_id, payload)
    await role_notification_management.send_role_update_notification(
        before_data=before_data,
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)


@router.put("/{role_id}/permissions")
async def assign_role_permissions(
    role_id: Annotated[int, Path(ge=1)],
    payload: RoleAssignPermissionRequest,
    request: Request,
    role_management: Annotated[RoleManagement, Depends(get_role_management)],
    role_notification_management: Annotated[
        RoleNotificationManagement,
        Depends(get_role_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("role:assign_permission"))],
    operation_log: Annotated[None, Depends(operation_log_record("分配角色权限"))],
) -> dict:
    """给角色分配权限。

    用途：
        替换角色当前权限点列表，并清理绑定该角色用户的 RBAC 缓存。
    参数：
        role_id：角色 ID。
        payload：分配权限请求参数。
        role_management：角色管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含角色 ID 和新的权限 ID 列表。
    """

    role = await role_management.get_role(role_id)
    before_permissions = await role_management.list_role_permissions(role_id)
    data = await role_management.assign_permissions(role_id, payload)
    after_permissions = await role_management.list_role_permissions(role_id)
    await role_notification_management.send_role_assign_permission_notification(
        role=role,
        before_permissions=before_permissions,
        after_permissions=after_permissions,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)
