from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from loguru import logger

from services.oa_admin.apps.auth.deps.auth_deps import login_check
from services.oa_admin.apps.auth.models.auth import CurrentUser
from services.oa_admin.apps.operation_log.managements.operation_log_management import (
    OperationLogManagement,
)
from services.oa_admin.apps.operation_log.models.operation_log import OperationLogCreate
from services.oa_admin.db.mysql import get_mysql_pool

MySQLPoolDep = Annotated[Any, Depends(get_mysql_pool)]


def get_operation_log_management(mysql_pool: MySQLPoolDep) -> OperationLogManagement:
    """组装操作日志管理业务对象。

    用途：
        从 FastAPI 依赖中注入 MySQL，并创建 OperationLogManagement。
    参数：
        mysql_pool：MySQL 异步连接池。
    返回值：
        OperationLogManagement 实例。
    """

    return OperationLogManagement(mysql_pool=mysql_pool)


def operation_log_record(action: str) -> Callable[..., AsyncIterator[None]]:
    """创建操作日志记录依赖。

    用途：
        为后台关键写操作生成 FastAPI Depends 依赖，在接口成功或失败后写入审计日志。
    参数：
        action：操作动作名称，例如“创建用户”。
    返回值：
        可被 Depends 使用的异步 yield 依赖函数。
    """

    async def recorder(
        request: Request,
        current_user: Annotated[CurrentUser, Depends(login_check)],
        mysql_pool: MySQLPoolDep,
    ) -> AsyncIterator[None]:
        """记录单次操作日志。

        用途：
            包裹路由执行过程，路由成功时记录“成功”，路由抛异常时记录“失败”。
        参数：
            request：当前 HTTP 请求对象。
            current_user：当前登录用户。
            mysql_pool：MySQL 异步连接池。
        返回值：
            异步生成器，无业务返回值。
        """

        try:
            yield
        except Exception:
            await _write_operation_log(mysql_pool, request, current_user, action, "失败")
            raise
        else:
            await _write_operation_log(mysql_pool, request, current_user, action, "成功")

    return recorder


async def _write_operation_log(
    mysql_pool: Any,
    request: Request,
    current_user: CurrentUser,
    action: str,
    result: str,
) -> None:
    """写入单条操作日志。

    用途：
        从请求上下文组装审计字段并写入数据库；写入失败只记录日志，不影响原业务接口。
    参数：
        mysql_pool：MySQL 异步连接池。
        request：当前 HTTP 请求对象。
        current_user：当前登录用户。
        action：操作动作名称。
        result：操作结果，成功或失败。
    返回值：
        无返回值。
    """

    request_id = str(getattr(request.state, "request_id", ""))
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip()
    if not client_ip and request.client:
        client_ip = request.client.host

    payload = OperationLogCreate(
        user_id=current_user.user_id,
        request_id=request_id,
        action=action,
        path=request.url.path,
        method=request.method,
        ip=client_ip,
        result=result,
    )
    try:
        manager = OperationLogManagement(mysql_pool=mysql_pool)
        await manager.create_operation_log(payload)
    except Exception as exc:
        logger.exception(
            "operation log write failed request_id={} action={} result={} error={}",
            request_id,
            action,
            result,
            exc,
        )
