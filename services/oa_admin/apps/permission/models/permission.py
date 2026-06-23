from typing import Literal

from pydantic import BaseModel, Field

PermissionType = Literal["menu", "button", "api"] # 权限类型


class PermissionListQuery(BaseModel):
    """权限列表查询模型。

    用途：
        描述权限列表接口支持的筛选条件。
    参数：
        keyword：权限编码或权限名称关键字。
        perm_type：权限类型，可选 menu、button、api。
        status：权限状态，1 启用，0 禁用。
        parent_id：父级权限 ID。
    返回值：
        Pydantic 查询模型实例。
    """

    keyword: str | None = Field(default=None, max_length=100)
    perm_type: PermissionType | None = None
    status: int | None = Field(default=None, ge=0, le=1)
    parent_id: int | None = Field(default=None, ge=0)


class PermissionCreateRequest(BaseModel):
    """创建权限点请求模型。

    用途：
        描述创建 sys_permission 权限点需要的字段。
    参数：
        perm_code：权限编码，创建后不允许修改。
        perm_name：权限名称。
        perm_type：权限类型，可选 menu、button、api。
        parent_id：父级权限 ID，0 表示顶级权限。
        path：接口路径或前端菜单路径。
        method：HTTP 方法。
        status：权限状态，1 启用，0 禁用。
        sort：排序值。
    返回值：
        Pydantic 请求模型实例。
    """

    perm_code: str = Field(min_length=1, max_length=100)
    perm_name: str = Field(min_length=1, max_length=100)
    perm_type: PermissionType
    parent_id: int = Field(default=0, ge=0)
    path: str = Field(default="", max_length=255)
    method: str = Field(default="", max_length=20)
    status: int = Field(default=1, ge=0, le=1)
    sort: int = 0


class PermissionUpdateRequest(BaseModel):
    """更新权限点请求模型。

    用途：
        描述权限点允许更新的字段，perm_code 不允许更新。
    参数：
        perm_name：权限名称。
        perm_type：权限类型，可选 menu、button、api。
        parent_id：父级权限 ID，0 表示顶级权限。
        path：接口路径或前端菜单路径。
        method：HTTP 方法。
        status：权限状态，1 启用，0 禁用。
        sort：排序值。
    返回值：
        Pydantic 请求模型实例。
    """

    perm_name: str = Field(min_length=1, max_length=100)
    perm_type: PermissionType
    parent_id: int = Field(default=0, ge=0)
    path: str = Field(default="", max_length=255)
    method: str = Field(default="", max_length=20)
    status: int = Field(default=1, ge=0, le=1)
    sort: int = 0


class PermissionInfo(BaseModel):
    """权限点信息模型。

    用途：
        描述权限管理接口返回给前端的权限点数据。
    参数：
        id：权限点 ID。
        perm_code：权限编码。
        perm_name：权限名称。
        perm_type：权限类型。
        parent_id：父级权限 ID。
        path：接口路径或前端菜单路径。
        method：HTTP 方法。
        status：权限状态。
        sort：排序值。
    返回值：
        Pydantic 响应模型实例。
    """

    id: int
    perm_code: str
    perm_name: str
    perm_type: str
    parent_id: int
    path: str
    method: str
    status: int
    sort: int
