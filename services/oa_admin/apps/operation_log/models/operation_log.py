from datetime import datetime

from pydantic import BaseModel, Field


class OperationLogListQuery(BaseModel):
    """操作日志列表查询模型。

    用途：
        描述操作日志列表接口支持的筛选条件和分页参数。
    参数：
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        result：操作结果，成功或失败。
        start_time：创建时间开始值。
        end_time：创建时间结束值。
        page：当前页码，从 1 开始。
        page_size：每页数量。
    返回值：
        Pydantic 查询模型实例。
    """

    user_id: int | None = Field(default=None, ge=1)
    request_id: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=20)
    result: str | None = Field(default=None, max_length=30)
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class OperationLogCreate(BaseModel):
    """操作日志创建模型。

    用途：
        描述写入 sys_operation_log 需要的字段。
    参数：
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        ip：客户端 IP。
        result：操作结果，成功或失败。
    返回值：
        Pydantic 创建模型实例。
    """

    user_id: int
    request_id: str = Field(default="", max_length=64)
    action: str = Field(max_length=100)
    path: str = Field(default="", max_length=255)
    method: str = Field(default="", max_length=20)
    ip: str = Field(default="", max_length=64)
    result: str = Field(max_length=30)


class OperationLogInfo(BaseModel):
    """操作日志信息模型。

    用途：
        描述操作日志查询接口返回给前端的日志数据。
    参数：
        id：操作日志 ID。
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        ip：客户端 IP。
        result：操作结果。
        created_at：创建时间。
    返回值：
        Pydantic 响应模型实例。
    """

    id: int
    user_id: int | None
    request_id: str
    action: str
    path: str
    method: str
    ip: str
    result: str
    created_at: datetime


class OperationLogListResponse(BaseModel):
    """操作日志列表响应模型。

    用途：
        描述操作日志分页列表返回结构。
    参数：
        items：当前页日志列表。
        total：符合条件的日志总数。
        page：当前页码。
        page_size：每页数量。
    返回值：
        Pydantic 响应模型实例。
    """

    items: list[OperationLogInfo]
    total: int
    page: int
    page_size: int
