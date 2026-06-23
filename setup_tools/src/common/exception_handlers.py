from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette import status

from common.exceptions import BusinessException
from common.response import fail

HTTP_EXCEPTION_MSG_MAP = {
    status.HTTP_401_UNAUTHORIZED: "未登录或登录已失效",
    status.HTTP_403_FORBIDDEN: "无权限访问",
    status.HTTP_404_NOT_FOUND: "资源不存在",
}


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理器。

    用途：
        将 FastAPI、参数校验、业务异常和未知异常转换为统一响应结构。
    参数：
        app：FastAPI 应用实例。
    返回值：
        无返回值，函数会直接修改传入的应用实例。
    """

    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unknown_exception_handler)


async def business_exception_handler(request: Request, exc: BusinessException) -> JSONResponse:
    """处理业务异常。

    用途：
        将业务层主动抛出的异常转换为统一 JSON 响应。
    参数：
        request：当前请求对象，用于读取 request_id 等上下文。
        exc：业务异常实例。
    返回值：
        统一格式的 JSON 响应。
    """

    request_id = getattr(request.state, "request_id", "")
    logger.warning("business exception request_id={} code={} msg={}", request_id, exc.code, exc.msg)
    return JSONResponse(status_code=status.HTTP_200_OK, content=fail(exc.code, exc.msg, exc.data))


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """处理请求参数校验异常。

    用途：
        将 Pydantic 参数校验错误转换为统一 JSON 响应，避免直接暴露框架默认结构。
    参数：
        request：当前请求对象。
        exc：FastAPI 参数校验异常。
    返回值：
        统一格式的 JSON 响应。
    """

    request_id = getattr(request.state, "request_id", "")
    logger.warning("validation exception request_id={} errors={}", request_id, exc.errors())
    return JSONResponse(status_code=status.HTTP_200_OK, content=fail(40000, "参数错误"))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTP 异常。

    用途：
        将 FastAPI 抛出的 HTTPException 转换为统一 JSON 响应。
    参数：
        request：当前请求对象。
        exc：HTTP 异常实例。
    返回值：
        统一格式的 JSON 响应。
    """

    request_id = getattr(request.state, "request_id", "")
    logger.warning(
        "http exception request_id={} status={} detail={}",
        request_id,
        exc.status_code,
        exc.detail,
    )
    code = 40400 if exc.status_code == status.HTTP_404_NOT_FOUND else exc.status_code
    msg = HTTP_EXCEPTION_MSG_MAP.get(exc.status_code, "请求失败")
    return JSONResponse(status_code=exc.status_code, content=fail(code, msg))


async def unknown_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未知系统异常。

    用途：
        捕获未预期异常并返回统一错误结构，同时记录完整异常日志。
    参数：
        request：当前请求对象。
        exc：未知异常实例。
    返回值：
        统一格式的 JSON 响应。
    """

    request_id = getattr(request.state, "request_id", "")
    logger.exception("unknown exception request_id={} error={}", request_id, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=fail(50000, "系统异常"),
    )
