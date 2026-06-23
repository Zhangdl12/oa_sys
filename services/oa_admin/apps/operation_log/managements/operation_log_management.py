from typing import Any

from common.exceptions import BusinessException

from services.oa_admin.apps.operation_log.crud.operation_log_crud import (
    count_operation_logs,
    get_operation_log_by_id,
    insert_operation_log,
    list_operation_logs,
)
from services.oa_admin.apps.operation_log.models.operation_log import (
    OperationLogCreate,
    OperationLogInfo,
    OperationLogListQuery,
    OperationLogListResponse,
)


class OperationLogManagement:
    """操作日志管理业务对象。

    用途：
        负责编排操作日志写入、分页列表查询和详情查询。
    参数：
        mysql_pool：MySQL 异步连接池。
    返回值：
        操作日志管理业务对象实例。
    """

    def __init__(self, mysql_pool: Any) -> None:
        self.mysql_pool = mysql_pool

    async def list_operation_logs(self, query: OperationLogListQuery) -> dict[str, Any]:
        """查询操作日志列表。

        用途：
            根据筛选条件分页查询操作日志，并转换为统一响应数据。
        参数：
            query：操作日志列表查询条件。
        返回值：
            包含 items、total、page、page_size 的分页字典。
        """

        offset = (query.page - 1) * query.page_size
        total = await count_operation_logs(
            self.mysql_pool,
            user_id=query.user_id,
            request_id=query.request_id,
            action=query.action,
            path=query.path,
            method=query.method,
            result=query.result,
            start_time=query.start_time,
            end_time=query.end_time,
        )
        rows = await list_operation_logs(
            self.mysql_pool,
            user_id=query.user_id,
            request_id=query.request_id,
            action=query.action,
            path=query.path,
            method=query.method,
            result=query.result,
            start_time=query.start_time,
            end_time=query.end_time,
            offset=offset,
            limit=query.page_size,
        )
        response = OperationLogListResponse(
            items=[OperationLogInfo.model_validate(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        return response.model_dump()

    async def get_operation_log(self, log_id: int) -> dict[str, Any]:
        """查询操作日志详情。

        用途：
            按日志 ID 查询单条操作日志详情。
        参数：
            log_id：操作日志 ID。
        返回值：
            操作日志详情字典。
        """

        row = await get_operation_log_by_id(self.mysql_pool, log_id)
        if not row:
            raise BusinessException(code=40400, msg="操作日志不存在")
        return OperationLogInfo.model_validate(row).model_dump()

    async def create_operation_log(self, payload: OperationLogCreate) -> int:
        """写入操作日志。

        用途：
            将后台关键操作写入 sys_operation_log。
        参数：
            payload：操作日志创建模型。
        返回值：
            新增操作日志 ID。
        """

        return await insert_operation_log(self.mysql_pool, payload.model_dump())
