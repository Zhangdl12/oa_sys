from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends, Path, Request

from services.oa_admin.apps.auth.deps.auth_deps import permission_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.operation_log.deps.operation_log_deps import operation_log_record
from services.oa_admin.apps.user.deps.user_deps import (
    get_user_management,
    get_user_notification_management,
)
from services.oa_admin.apps.user.managements.user_management import UserManagement
from services.oa_admin.apps.user.managements.user_notification_management import (
    UserNotificationManagement,
)
from services.oa_admin.apps.user.models.user import (
    UserCreateRequest,
    UserListQuery,
    UserUpdateRequest,
)

router = APIRouter()


@router.get("")
async def list_users(
    query: Annotated[UserListQuery, Depends()],
    user_management: Annotated[UserManagement, Depends(get_user_management)],
    current_user: Annotated[CurrentUser, Depends(permission_check("user:list"))],
) -> dict:
    """查询用户列表。

    用途：
        查询系统用户，供后台用户管理列表展示和筛选使用。
    参数：
        query：用户列表筛选条件。
        user_management：用户管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含用户列表。
    """

    data = await user_management.list_users(query)
    return success(data)


@router.get("/{user_id}")
async def get_user(
    user_id: Annotated[int, Path(ge=1)],
    user_management: Annotated[UserManagement, Depends(get_user_management)],
    current_user: Annotated[CurrentUser, Depends(permission_check("user:list"))],
) -> dict:
    """查询用户详情。

    用途：
        根据用户 ID 查询单个用户的基础信息。
    参数：
        user_id：用户 ID。
        user_management：用户管理业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制。
    返回值：
        统一响应结构，data 中包含用户详情。
    """

    data = await user_management.get_user(user_id)
    return success(data)


@router.post("")
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    user_management: Annotated[UserManagement, Depends(get_user_management)],
    user_notification_management: Annotated[
        UserNotificationManagement,
        Depends(get_user_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("user:create"))],
    operation_log: Annotated[None, Depends(operation_log_record("创建用户"))],
) -> dict:
    """创建用户。

    用途：
        新增系统用户，并在创建成功后按配置发送用户创建通知。
    参数：
        payload：创建用户请求参数。
        request：FastAPI 请求对象，用于读取 request_id。
        user_management：用户管理业务对象，由 deps 层组装。
        user_notification_management：用户通知业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制和通知操作人。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含创建后的用户。
    """

    data = await user_management.create_user(payload)
    await user_notification_management.send_user_create_notification(
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)


@router.put("/{user_id}")
async def update_user(
    user_id: Annotated[int, Path(ge=1)],
    payload: UserUpdateRequest,
    request: Request,
    user_management: Annotated[UserManagement, Depends(get_user_management)],
    user_notification_management: Annotated[
        UserNotificationManagement,
        Depends(get_user_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("user:update"))],
    operation_log: Annotated[None, Depends(operation_log_record("更新用户"))],
) -> dict:
    """更新用户。

    用途：
        更新用户基础资料、角色和状态。
    参数：
        user_id：用户 ID。
        payload：更新用户请求参数。
        request：FastAPI 请求对象，用于读取 request_id。
        user_management：用户管理业务对象，由 deps 层组装。
        user_notification_management：用户通知业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制和通知操作人。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含更新后的用户。
    """

    before_data = await user_management.get_user(user_id)
    data = await user_management.update_user(user_id, payload)
    await user_notification_management.send_user_update_notification(
        before_data=before_data,
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)


@router.delete("/{user_id}")
async def delete_user(
    user_id: Annotated[int, Path(ge=1)],
    request: Request,
    user_management: Annotated[UserManagement, Depends(get_user_management)],
    user_notification_management: Annotated[
        UserNotificationManagement,
        Depends(get_user_notification_management),
    ],
    current_user: Annotated[CurrentUser, Depends(permission_check("user:delete"))],
    operation_log: Annotated[None, Depends(operation_log_record("删除用户"))],
) -> dict:
    """删除用户。

    用途：
        真实删除用户，并清理该用户的登录态和权限缓存。
    参数：
        user_id：用户 ID。
        request：FastAPI 请求对象，用于读取 request_id。
        user_management：用户管理业务对象，由 deps 层组装。
        user_notification_management：用户通知业务对象，由 deps 层组装。
        current_user：permission_check 注入的当前用户，仅用于权限控制和通知操作人。
        operation_log：操作日志依赖，仅用于记录审计日志。
    返回值：
        统一响应结构，data 中包含删除前的用户快照。
    """

    data = await user_management.delete_user(user_id, current_user.user_id)
    await user_notification_management.send_user_delete_notification(
        data=data,
        current_user=current_user,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return success(data)
