from datetime import datetime
from typing import Any

NOTIFY_LOG_SELECT_COLUMNS = """
id,
platform,
notify_type,
receive_id_type,
receive_id,
content_summary,
sender_user_id,
request_id,
result,
external_message_id,
error_msg,
created_at
"""


def _build_list_where(
    platform: str | None = None,
    receive_id: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[str, list[Any]]:
    """构造通知记录列表查询条件。

    用途：
        为列表和总数查询复用 WHERE 子句和 SQL 参数。
    """

    where_parts: list[str] = []
    params: list[Any] = []
    if platform:
        where_parts.append("platform = %s")
        params.append(platform)
    if receive_id:
        where_parts.append("receive_id = %s")
        params.append(receive_id)
    if result:
        where_parts.append("result = %s")
        params.append(result)
    if start_time is not None:
        where_parts.append("created_at >= %s")
        params.append(start_time)
    if end_time is not None:
        where_parts.append("created_at <= %s")
        params.append(end_time)

    if not where_parts:
        return "", params
    return "WHERE " + " AND ".join(where_parts), params


async def insert_notify_log(mysql_pool: Any, payload: dict[str, Any]) -> int:
    """新增外部通知发送记录。

    参数：
        mysql_pool：MySQL 异步连接池。
        payload：已经由业务层组装好的通知记录字段。
    返回值：
        新增通知记录 ID。
    """

    sql = """
    INSERT INTO sys_external_notify_log (
        platform,
        notify_type,
        receive_id_type,
        receive_id,
        content_summary,
        sender_user_id,
        request_id,
        result,
        external_message_id,
        error_msg
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        payload["platform"],
        payload["notify_type"],
        payload["receive_id_type"],
        payload["receive_id"],
        payload["content_summary"],
        payload["sender_user_id"],
        payload["request_id"],
        payload["result"],
        payload["external_message_id"],
        payload["error_msg"],
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()
            return int(cursor.lastrowid)


async def list_notify_logs(
    mysql_pool: Any,
    platform: str | None = None,
    receive_id: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """分页查询外部通知发送记录。

    返回值：
        通知记录字典列表。
    """

    where_sql, params = _build_list_where(
        platform=platform,
        receive_id=receive_id,
        result=result,
        start_time=start_time,
        end_time=end_time,
    )
    sql = f"""
    SELECT {NOTIFY_LOG_SELECT_COLUMNS}
    FROM sys_external_notify_log
    {where_sql}
    ORDER BY id DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            return await cursor.fetchall()


async def count_notify_logs(
    mysql_pool: Any,
    platform: str | None = None,
    receive_id: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> int:
    """统计外部通知发送记录数量。

    返回值：
        符合筛选条件的记录总数。
    """

    where_sql, params = _build_list_where(
        platform=platform,
        receive_id=receive_id,
        result=result,
        start_time=start_time,
        end_time=end_time,
    )
    sql = f"""
    SELECT COUNT(*) AS total
    FROM sys_external_notify_log
    {where_sql}
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            row = await cursor.fetchone()
            return int(row["total"]) if row else 0
