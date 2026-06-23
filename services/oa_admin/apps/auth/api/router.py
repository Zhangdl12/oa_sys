from typing import Annotated

from common.response import success
from fastapi import APIRouter, Depends

from services.oa_admin.apps.auth.deps.auth_deps import (
    get_auth_management,
    login_check,
    permission_check,
)
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import CurrentUser, LoginRequest

router = APIRouter()


@router.post("/login")
async def login(
    payload: LoginRequest,
    auth_management: Annotated[AuthManagement, Depends(get_auth_management)],
) -> dict:
    """用户登录。

    用途：
        接收账号密码并调用认证业务对象完成 JWT 生成和 Redis 登录态写入。
    参数：
        payload：登录请求参数。
        auth_management：认证业务对象，由 deps 层组装。
    返回值：
        统一响应结构，data 中包含 access_token、token_type、expires_in 和 user。
    """

    login_result = await auth_management.login(payload)
    return success(login_result)


@router.post("/logout")
async def logout(
    current_user: Annotated[CurrentUser, Depends(login_check)],
    auth_management: Annotated[AuthManagement, Depends(get_auth_management)],
) -> dict:
    """用户退出登录。

    用途：
        删除当前 token 对应的 Redis 登录态，不影响同用户其他设备登录。
    参数：
        current_user：login_check 注入的当前用户。
        auth_management：认证业务对象，由 deps 层组装。
    返回值：
        统一成功响应。
    """

    await auth_management.logout(current_user)
    return success()


@router.get("/me")
async def get_me(current_user: Annotated[CurrentUser, Depends(login_check)]) -> dict:
    """获取当前登录用户。

    用途：
        返回当前 token 对应的用户基础信息。
    参数：
        current_user：login_check 注入的当前用户。
    返回值：
        统一响应结构，data 中包含当前用户信息。
    """

    return success(current_user.model_dump(exclude={"jti"}))


@router.get("/rbac-check")
async def check_rbac(
    current_user: Annotated[CurrentUser, Depends(permission_check("user:list"))],
) -> dict:
    """验证 RBAC 权限校验。

    用途：
        为当前阶段验证 permission_check 权限依赖是否可用，不承载正式业务管理功能。
    参数：
        current_user：permission_check 校验通过后注入的当前用户。
    返回值：
        统一响应结构，data 中返回当前用户 ID 和已验证的权限编码。
    """

    return success({"user_id": current_user.user_id, "permission": "user:list"})
