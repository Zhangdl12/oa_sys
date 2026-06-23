from pydantic import BaseModel, Field


class UserListQuery(BaseModel):
    """用户列表查询模型。

    用途：
        描述用户列表接口支持的筛选条件。
    参数：
        keyword：登录账号、真实姓名、手机号或邮箱关键字。
        status：用户状态，1 启用，0 禁用。
        role_id：用户所属角色 ID。
    返回值：
        Pydantic 查询模型实例。
    """

    keyword: str | None = Field(default=None, max_length=100)
    status: int | None = Field(default=None, ge=0, le=1)
    role_id: int | None = Field(default=None, ge=1)


class UserCreateRequest(BaseModel):
    """创建用户请求模型。

    用途：
        描述创建 sys_user 用户需要的字段。
    参数：
        username：登录账号，创建后不在当前接口中修改。
        password：登录密码，写入数据库前会转换为 password_hash。
        real_name：真实姓名。
        mobile：手机号。
        email：邮箱。
        role_id：用户所属角色 ID。
        status：用户状态，1 启用，0 禁用。
    返回值：
        Pydantic 请求模型实例。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    real_name: str = Field(default="", max_length=100)
    mobile: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=120)
    role_id: int = Field(ge=1)
    status: int = Field(default=1, ge=0, le=1)


class UserUpdateRequest(BaseModel):
    """更新用户请求模型。

    用途：
        描述用户允许更新的字段，username 和 password 不在当前接口中修改。
    参数：
        real_name：真实姓名。
        mobile：手机号。
        email：邮箱。
        role_id：用户所属角色 ID。
        status：用户状态，1 启用，0 禁用。
    返回值：
        Pydantic 请求模型实例。
    """

    real_name: str = Field(default="", max_length=100)
    mobile: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=120)
    role_id: int = Field(ge=1)
    status: int = Field(default=1, ge=0, le=1)


class UserInfo(BaseModel):
    """用户信息模型。

    用途：
        描述用户管理接口返回给前端的用户数据，不包含 password_hash。
    参数：
        id：用户 ID。
        username：登录账号。
        real_name：真实姓名。
        mobile：手机号。
        email：邮箱。
        role_id：用户所属角色 ID。
        role_name：用户所属角色名称。
        status：用户状态。
        token_version：Token 版本，用于判断旧 token 是否失效。
    返回值：
        Pydantic 响应模型实例。
    """

    id: int
    username: str
    real_name: str
    mobile: str
    email: str
    role_id: int
    role_name: str = ""
    status: int
    token_version: int
