from typing import Any

from common.exceptions import BusinessException
from common.security import create_access_token, digest_token, verify_password

from services.oa_admin.apps.auth.constants import LOGIN_TOKEN_KEY_TEMPLATE
from services.oa_admin.apps.auth.models.auth import (
    AuthUserInfo,
    CurrentUser,
    LoginRequest,
    LoginResponse,
    TokenState,
)
from services.oa_admin.apps.user.crud.user_crud import get_user_by_username
from services.oa_admin.core.config import Settings


class AuthManagement:
    """认证业务对象。

    用途：
        负责登录、退出登录等认证流程编排，API 层不直接处理 JWT、Redis 或数据库细节。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
        settings：应用配置对象。
    返回值：
        认证业务对象实例。
    """

    def __init__(self, mysql_pool: Any, redis_client: Any, settings: Settings) -> None:
        self.mysql_pool = mysql_pool
        self.redis_client = redis_client
        self.settings = settings

    async def login(self, payload: LoginRequest) -> dict[str, Any]:
        """用户登录。

        用途：
            校验账号密码，生成 JWT，并把本次 token 摘要写入 Redis 登录态。
        参数：
            payload：登录请求参数。
        返回值：
            登录响应字典，包含 access_token、token_type、expires_in 和 user。
        """

        user = await get_user_by_username(self.mysql_pool, payload.username)
        if not user or not verify_password(payload.password, str(user["password_hash"])):
            raise BusinessException(code=40100, msg="用户名或密码错误")
        if int(user["status"]) != 1:
            raise BusinessException(code=40300, msg="用户已禁用")

        access_token = create_access_token(
            self.settings,
            {
                "user_id": int(user["id"]),
                "username": str(user["username"]),
                "role_id": int(user["role_id"]),
                "token_version": int(user["token_version"]),
            },
        )
        redis_key = LOGIN_TOKEN_KEY_TEMPLATE.format(user_id=user["id"], jti=access_token.jti)
        token_state = TokenState(
            token_digest=digest_token(access_token.access_token),
            username=str(user["username"]),
            role_id=int(user["role_id"]),
        )
        await self.redis_client.set(
            redis_key,
            token_state.model_dump_json(),
            ex=access_token.expires_in,
        )

        response = LoginResponse(
            access_token=access_token.access_token,
            expires_in=access_token.expires_in,
            user=AuthUserInfo(
                user_id=int(user["id"]),
                username=str(user["username"]),
                real_name=str(user.get("real_name") or ""),
                role_id=int(user["role_id"]),
            ),
        )
        return response.model_dump()

    async def logout(self, current_user: CurrentUser) -> None:
        """退出登录。

        用途：
            删除当前 token 对应的 Redis 登录态，不影响同用户其他 token。
        参数：
            current_user：当前登录用户。
        返回值：
            无返回值。
        """

        redis_key = LOGIN_TOKEN_KEY_TEMPLATE.format(
            user_id=current_user.user_id,
            jti=current_user.jti,
        )
        await self.redis_client.delete(redis_key)
