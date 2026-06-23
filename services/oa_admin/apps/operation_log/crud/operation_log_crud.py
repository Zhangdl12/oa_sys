from datetime import datetime
from typing import Any

OPERATION_LOG_SELECT_COLUMNS = """
id,
user_id,
request_id,
action,
path,
method,
ip,
result,
created_at
"""


def _build_list_where(
    user_id: int | None = None,
    request_id: str | None = None,
    action: str | None = None,
    path: str | None = None,
    method: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[str, list[Any]]:
    """构造操作日志查询条件。

    用途：
        根据可选筛选条件构造 WHERE 子句和参数列表，供列表和总数查询复用。
    参数：
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        result：操作结果。
        start_time：创建时间开始值。
        end_time：创建时间结束值。
    返回值：
        WHERE SQL 片段和参数列表。
    """

    where_parts: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        where_parts.append("user_id = %s")
        params.append(user_id)
    if request_id:
        where_parts.append("request_id = %s")
        params.append(request_id)
    if action:
        where_parts.append("action LIKE %s")
        params.append(f"%{action}%")
    if path:
        where_parts.append("path LIKE %s")
        params.append(f"%{path}%")
    if method:
        where_parts.append("method = %s")
        params.append(method)
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


async def list_operation_logs(
    mysql_pool: Any,
    user_id: int | None = None,
    request_id: str | None = None,
    action: str | None = None,
    path: str | None = None,
    method: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """查询操作日志列表。

    用途：
        按可选条件分页查询 sys_operation_log 操作日志数据。
    参数：
        mysql_pool：MySQL 异步连接池。
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        result：操作结果。
        start_time：创建时间开始值。
        end_time：创建时间结束值。
        offset：分页偏移量。
        limit：每页数量。
    返回值：
        操作日志字典列表。
    """

    where_sql, params = _build_list_where(
        user_id=user_id,
        request_id=request_id,
        action=action,
        path=path,
        method=method,
        result=result,
        start_time=start_time,
        end_time=end_time,
    )
    sql = f"""
    SELECT {OPERATION_LOG_SELECT_COLUMNS}
    FROM sys_operation_log
    {where_sql}
    ORDER BY id DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            return await cursor.fetchall()


async def count_operation_logs(
    mysql_pool: Any,
    user_id: int | None = None,
    request_id: str | None = None,
    action: str | None = None,
    path: str | None = None,
    method: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> int:
    """统计操作日志数量。

    用途：
        按可选条件统计 sys_operation_log 操作日志数量，供分页列表使用。
    参数：
        mysql_pool：MySQL 异步连接池。
        user_id：操作用户 ID。
        request_id：请求链路 ID。
        action：操作动作。
        path：请求路径。
        method：HTTP 方法。
        result：操作结果。
        start_time：创建时间开始值。
        end_time：创建时间结束值。
    返回值：
        符合条件的日志总数。
    """

    where_sql, params = _build_list_where(
        user_id=user_id,
        request_id=request_id,
        action=action,
        path=path,
        method=method,
        result=result,
        start_time=start_time,
        end_time=end_time,
    )
    sql = f"""
    SELECT COUNT(*) AS total
    FROM sys_operation_log
    {where_sql}
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            row = await cursor.fetchone()
            return int(row["total"]) if row else 0


async def get_operation_log_by_id(mysql_pool: Any, log_id: int) -> dict[str, Any] | None:
    """按 ID 查询操作日志。

    用途：
        为操作日志详情接口提供单条日志查询。
    参数：
        mysql_pool：MySQL 异步连接池。
        log_id：操作日志 ID。
    返回值：
        查询到返回操作日志字典，否则返回 None。
    """

    sql = f"""
    SELECT {OPERATION_LOG_SELECT_COLUMNS}
    FROM sys_operation_log
    WHERE id = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (log_id,))
            return await cursor.fetchone()


async def insert_operation_log(mysql_pool: Any, payload: dict[str, Any]) -> int:
    """新增操作日志。

    用途：
        向 sys_operation_log 写入一条后台关键操作审计日志。
    参数：
        mysql_pool：MySQL 异步连接池。
        payload：已经通过业务层组装的操作日志字段。
    返回值：
        新增操作日志 ID。
    """

    sql = """
    INSERT INTO sys_operation_log (
        user_id,
        request_id,
        action,
        path,
        method,
        ip,
        result
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        payload["user_id"],
        payload["request_id"],
        payload["action"],
        payload["path"],
        payload["method"],
        payload["ip"],
        payload["result"],
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()
            return int(cursor.lastrowid)
