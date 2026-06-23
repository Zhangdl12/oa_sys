from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求模型。

    用途：
        描述用户登录接口需要接收的账号和密码。
    参数：
        username：登录账号。
        password：明文密码，只用于本次登录校验，不会落库。
    返回值：
        Pydantic 请求模型实例。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AuthUserInfo(BaseModel):
    """认证用户信息模型。

    用途：
        描述登录成功后返回给前端的最小用户信息。
    参数：
        user_id：用户 ID。
        username：登录账号。
        real_name：真实姓名。
        role_id：角色 ID。
    返回值：
        Pydantic 响应模型实例。
    """

    user_id: int
    username: str
    real_name: str
    role_id: int


class LoginResponse(BaseModel):
    """登录响应模型。

    用途：
        描述登录成功后返回的 token 信息和用户信息。
    参数：
        access_token：JWT 字符串。
        token_type：token 类型，固定为 bearer。
        expires_in：token 有效秒数。
        user：登录用户基础信息。
    返回值：
        Pydantic 响应模型实例。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserInfo


class CurrentUser(BaseModel):
    """当前登录用户模型。

    用途：
        login_check 校验通过后向业务接口注入当前登录用户信息。
    参数：
        user_id：用户 ID。
        username：登录账号。
        real_name：真实姓名。
        role_id：角色 ID。
        token_version：用户 token 版本。
        jti：当前 token 的唯一 ID，用于退出登录时删除 Redis 登录态。
    返回值：
        Pydantic 业务模型实例。
    """

    user_id: int
    username: str
    real_name: str
    role_id: int
    token_version: int
    jti: str


class TokenState(BaseModel):
    """Redis 登录态模型。

    用途：
        描述 Redis 中保存的 token 摘要和基础登录信息。
    参数：
        token_digest：JWT 摘要。
        username：登录账号。
        role_id：角色 ID。
    返回值：
        Pydantic 业务模型实例。
    """

    token_digest: str
    username: str
    role_id: int


class RbacPermissionCache(BaseModel):
    """Redis 权限缓存模型。

    用途：
        描述 Redis 中缓存的用户角色和权限编码列表，用于 RBAC 接口鉴权。
    参数：
        role_id：缓存生成时用户所属角色 ID。
        permissions：当前角色拥有的权限编码列表。
    返回值：
        Pydantic 业务模型实例。
    """

    role_id: int
    permissions: list[str]
