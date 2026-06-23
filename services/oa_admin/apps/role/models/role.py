from pydantic import BaseModel, Field


class RoleListQuery(BaseModel):
    """角色列表查询模型。

    用途：
        描述角色列表接口支持的筛选条件。
    参数：
        keyword：角色编码或角色名称关键字。
        status：角色状态，1 启用，0 禁用。
    返回值：
        Pydantic 查询模型实例。
    """

    keyword: str | None = Field(default=None, max_length=100)
    status: int | None = Field(default=None, ge=0, le=1)


class RoleCreateRequest(BaseModel):
    """创建角色请求模型。

    用途：
        描述创建 sys_role 角色需要的字段。
    参数：
        role_code：角色编码，创建后不允许修改。
        role_name：角色名称。
        status：角色状态，1 启用，0 禁用。
        remark：角色备注。
    返回值：
        Pydantic 请求模型实例。
    """

    role_code: str = Field(min_length=1, max_length=64)
    role_name: str = Field(min_length=1, max_length=100)
    status: int = Field(default=1, ge=0, le=1)
    remark: str = Field(default="", max_length=255)


class RoleUpdateRequest(BaseModel):
    """更新角色请求模型。

    用途：
        描述角色允许更新的字段，role_code 不允许更新。
    参数：
        role_name：角色名称。
        status：角色状态，1 启用，0 禁用。
        remark：角色备注。
    返回值：
        Pydantic 请求模型实例。
    """

    role_name: str = Field(min_length=1, max_length=100)
    status: int = Field(default=1, ge=0, le=1)
    remark: str = Field(default="", max_length=255)


class RoleAssignPermissionRequest(BaseModel):
    """角色分配权限请求模型。

    用途：
        描述给角色分配权限时提交的权限 ID 列表。
    参数：
        permission_ids：权限 ID 列表，允许为空列表表示清空角色权限。
    返回值：
        Pydantic 请求模型实例。
    """

    permission_ids: list[int] = Field(default_factory=list)


class RoleInfo(BaseModel):
    """角色信息模型。

    用途：
        描述角色管理接口返回给前端的角色数据。
    参数：
        id：角色 ID。
        role_code：角色编码。
        role_name：角色名称。
        status：角色状态。
        remark：角色备注。
    返回值：
        Pydantic 响应模型实例。
    """

    id: int
    role_code: str
    role_name: str
    status: int
    remark: str
