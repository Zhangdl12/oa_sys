from typing import Any

from services.oa_admin.apps.external.crud.notify_log_crud import (
    count_notify_logs,
    list_notify_logs,
)
from services.oa_admin.apps.external.models.notify_log import (
    ExternalNotifyLogInfo,
    ExternalNotifyLogListQuery,
    ExternalNotifyLogListResponse,
)


class ExternalNotifyLogManagement:
    """外部通知记录管理业务对象。

    用途：
        负责外部通知发送记录的分页查询和响应模型转换。
    """

    def __init__(self, mysql_pool: Any) -> None:
        self.mysql_pool = mysql_pool

    async def list_notify_logs(self, query: ExternalNotifyLogListQuery) -> dict[str, Any]:
        """分页查询外部通知发送记录。

        参数：
            query：通知记录筛选条件和分页参数。
        返回值：
            包含 items、total、page、page_size 的分页字典。
        """

        offset = (query.page - 1) * query.page_size
        total = await count_notify_logs(
            self.mysql_pool,
            platform=query.platform,
            receive_id=query.receive_id,
            result=query.result,
            start_time=query.start_time,
            end_time=query.end_time,
        )
        rows = await list_notify_logs(
            self.mysql_pool,
            platform=query.platform,
            receive_id=query.receive_id,
            result=query.result,
            start_time=query.start_time,
            end_time=query.end_time,
            offset=offset,
            limit=query.page_size,
        )
        response = ExternalNotifyLogListResponse(
            items=[ExternalNotifyLogInfo.model_validate(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        return response.model_dump()
