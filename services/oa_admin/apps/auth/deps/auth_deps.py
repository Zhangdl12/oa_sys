import json
from collections.abc import Callable
from typing import Annotated, Any

from common.exceptions import BusinessException
from common.security import decode_access_token, digest_token
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.oa_admin.apps.auth.constants import LOGIN_TOKEN_KEY_TEMPLATE, RBAC_USER_KEY_TEMPLATE
from services.oa_admin.apps.auth.managements.auth_management import AuthManagement
from services.oa_admin.apps.auth.models.auth import CurrentUser, RbacPermissionCache, TokenState
from services.oa_admin.apps.permission.crud.permission_crud import list_permission_codes_by_role_id
from services.oa_admin.apps.user.crud.user_crud import get_user_by_id
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.db.mysql import get_mysql_pool
from services.oa_admin.db.redis import get_redis_client

bearer_scheme = HTTPBearer(auto_error=False)

MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]
RedisClientDep = Annotated[Any, Depends(get_redis_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
BearerCredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_auth_management(
    mysql_pool: MySQLPoolDep,
    redis_client: RedisClientDep,
    settings: SettingsDep,
) -> AuthManagement:
    """组装认证业务对象。

    用途：
        从 FastAPI 依赖中注入 MySQL、Redis 和配置对象，并创建 AuthManagement。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
        settings：应用配置对象。
    返回值：
        AuthManagement 实例。
    """

    return AuthManagement(mysql_pool=mysql_pool, redis_client=redis_client, settings=settings)


async def login_check(
    credentials: BearerCredentialsDep,
    mysql_pool: MySQLPoolDep,
    redis_client: RedisClientDep,
    settings: SettingsDep,
) -> CurrentUser:
    """校验当前登录态。

    用途：
        校验 Bearer JWT、Redis 登录态、用户状态和 token_version，并返回当前用户。
    参数：
        credentials：HTTP Bearer 认证信息。
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
        settings：应用配置对象。
    返回值：
        CurrentUser 当前用户模型。
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise BusinessException(code=40100, msg="缺少登录凭证")

    token = credentials.credentials
    payload = decode_access_token(settings, token)
    user_id = payload.get("user_id")
    jti = payload.get("jti")
    token_version = payload.get("token_version")

    if not user_id or not jti or token_version is None:
        raise BusinessException(code=40100, msg="登录凭证无效")

    redis_key = LOGIN_TOKEN_KEY_TEMPLATE.format(user_id=user_id, jti=jti)
    token_state_text = await redis_client.get(redis_key)
    if not token_state_text:
        raise BusinessException(code=40100, msg="登录已过期")

    try:
        token_state = TokenState.model_validate(json.loads(token_state_text))
    except (json.JSONDecodeError, ValueError) as exc:
        raise BusinessException(code=40100, msg="登录状态异常") from exc

    if token_state.token_digest != digest_token(token):
        raise BusinessException(code=40100, msg="登录凭证无效")

    user = await get_user_by_id(mysql_pool, int(user_id))
    if not user:
        raise BusinessException(code=40100, msg="登录凭证无效")
    if int(user["status"]) != 1:
        raise BusinessException(code=40300, msg="用户已禁用")
    if int(user["token_version"]) != int(token_version):
        raise BusinessException(code=40100, msg="登录已过期")

    return CurrentUser(
        user_id=int(user["id"]),
        username=str(user["username"]),
        real_name=str(user.get("real_name") or ""),
        role_id=int(user["role_id"]),
        token_version=int(user["token_version"]),
        jti=str(jti),
    )


async def _load_rbac_cache(redis_client: Any, user_id: int) -> RbacPermissionCache | None:
    """读取用户权限缓存。

    用途：
        从 Redis 读取 `oa:rbac:user:{user_id}`，并转换为权限缓存模型。
    参数：
        redis_client：Redis 异步客户端。
        user_id：当前登录用户 ID。
    返回值：
        缓存有效时返回 RbacPermissionCache；缓存不存在或内容损坏时返回 None。
    """

    redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=user_id)
    cache_text = await redis_client.get(redis_key)
    if not cache_text:
        return None
    try:
        return RbacPermissionCache.model_validate(json.loads(cache_text))
    except (json.JSONDecodeError, ValueError):
        return None


async def _save_rbac_cache(
    redis_client: Any,
    settings: Settings,
    current_user: CurrentUser,
    permissions: list[str],
) -> None:
    """写入用户权限缓存。

    用途：
        将用户当前角色和权限编码列表写入 Redis，降低后续权限校验查库次数。
    参数：
        redis_client：Redis 异步客户端。
        settings：应用配置对象，提供权限缓存 TTL。
        current_user：当前登录用户。
        permissions：当前角色拥有的权限编码列表。
    返回值：
        无返回值。
    """

    redis_key = RBAC_USER_KEY_TEMPLATE.format(user_id=current_user.user_id)
    cache = RbacPermissionCache(role_id=current_user.role_id, permissions=permissions)
    await redis_client.set(redis_key, cache.model_dump_json(), ex=settings.rbac_cache_ttl_seconds)


async def _get_current_permissions(
    mysql_pool: Any,
    redis_client: Any,
    settings: Settings,
    current_user: CurrentUser,
) -> list[str]:
    """获取当前用户权限编码。

    用途：
        优先读取 Redis 权限缓存；缓存缺失、损坏或角色不一致时查询 MySQL 并刷新缓存。
    参数：
        mysql_pool：MySQL 异步连接池。
        redis_client：Redis 异步客户端。
        settings：应用配置对象。
        current_user：当前登录用户。
    返回值：
        当前用户角色拥有的权限编码列表。
    """

    cache = await _load_rbac_cache(redis_client, current_user.user_id)
    if cache and cache.role_id == current_user.role_id:
        return cache.permissions

    permissions = await list_permission_codes_by_role_id(mysql_pool, current_user.role_id)
    await _save_rbac_cache(redis_client, settings, current_user, permissions)
    return permissions


def permission_check(perm_code: str) -> Callable[..., Any]:
    """创建权限校验依赖。

    用途：
        为需要 RBAC 控制的接口生成 FastAPI Depends 依赖，校验当前用户是否拥有指定权限。
    参数：
        perm_code：接口要求的权限编码，例如 user:list。
    返回值：
        可被 Depends 使用的异步依赖函数；校验通过时返回 CurrentUser。
    """

    async def checker(
        current_user: Annotated[CurrentUser, Depends(login_check)],
        mysql_pool: MySQLPoolDep,
        redis_client: RedisClientDep,
        settings: SettingsDep,
    ) -> CurrentUser:
        """执行单个权限点校验。

        用途：
            检查当前用户权限编码列表中是否包含目标权限编码。
        参数：
            current_user：login_check 注入的当前登录用户。
            mysql_pool：MySQL 异步连接池。
            redis_client：Redis 异步客户端。
            settings：应用配置对象。
        返回值：
            权限校验通过后返回当前登录用户。
        """

        permissions = await _get_current_permissions(
            mysql_pool,
            redis_client,
            settings,
            current_user,
        )
        if perm_code not in permissions:
            raise BusinessException(code=40300, msg="无权限访问")
        return current_user

    return checker
