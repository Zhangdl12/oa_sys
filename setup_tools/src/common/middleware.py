from time import perf_counter
from uuid import uuid4

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestLogMiddleware(BaseHTTPMiddleware):
    """请求日志中间件。

    用途：
        为每个请求生成 request_id，并记录请求方法、路径、状态码和耗时。
    参数：
        app：Starlette/FastAPI 应用实例，由框架在注册中间件时传入。
    返回值：
        中间件实例，由 FastAPI 在请求生命周期中调用。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理单次 HTTP 请求。

        用途：
            写入请求上下文并记录访问日志，异常会继续抛给统一异常处理器。
        参数：
            request：当前 HTTP 请求对象。
            call_next：调用后续中间件或路由处理函数的回调。
        返回值：
            HTTP 响应对象。
        """

        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        start_time = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            cost_ms = round((perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "request failed request_id={} method={} path={} cost_ms={}",
                request_id,
                request.method,
                request.url.path,
                cost_ms,
            )
            raise

        cost_ms = round((perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request finished request_id={} method={} path={} status={} cost_ms={}",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
        )
        return response
