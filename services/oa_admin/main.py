from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.exception_handlers import register_exception_handlers
from common.http import close_http_client, create_http_client
from common.logger import configure_logger
from common.middleware import RequestLogMiddleware
from common.mysql import close_mysql_pool, create_mysql_pool
from common.redis import close_redis_client, create_redis_client
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from services.oa_admin.apps.router_init import api_router
from services.oa_admin.core.config import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理应用生命周期。

    用途：
        在 FastAPI 启动和关闭时统一初始化、释放 MySQL、Redis、HTTP 客户端等全局资源。
    参数：
        app：FastAPI 应用实例。
    返回值：
        异步上下文管理器，无直接返回业务数据。
    """

    settings = get_settings()
    configure_logger(settings)

    app.state.settings = settings
    app.state.mysql_pool = None
    app.state.redis_client = None
    app.state.http_client = create_http_client(settings)

    if settings.mysql_enabled:
        app.state.mysql_pool = await create_mysql_pool(settings)
        logger.info(
            "mysql pool initialized host={} database={}",
            settings.mysql_host,
            settings.mysql_database,
        )

    if settings.redis_enabled:
        app.state.redis_client = await create_redis_client(settings)
        logger.info("redis client initialized url={}", settings.redis_url)

    logger.info("application started app_name={} env={}", settings.app_name, settings.app_env)
    try:
        yield
    finally:
        await close_http_client(app.state.http_client)
        await close_redis_client(app.state.redis_client)
        await close_mysql_pool(app.state.mysql_pool)
        logger.info("application stopped app_name={}", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用实例。

    用途：
        集中注册应用生命周期、中间件、异常处理器和业务路由。
    参数：
        settings：可选配置对象，当前保留给后续测试覆盖使用。
    返回值：
        配置完成的 FastAPI 应用实例。
    """

    current_settings = settings or get_settings()
    app = FastAPI(
        title=current_settings.app_name,
        debug=current_settings.debug,
        lifespan=lifespan,
        openapi_url="/openapi.json" if current_settings.docs_enabled else None,
        docs_url="/docs" if current_settings.docs_enabled else None,
        redoc_url="/redoc" if current_settings.docs_enabled else None,
    )
    # 先写入默认 state，保证测试客户端或脚本导入时即使未进入 lifespan 也能读取基础状态。
    app.state.settings = current_settings
    app.state.mysql_pool = None
    app.state.redis_client = None
    app.state.http_client = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=current_settings.allowed_origins,
        allow_credentials=True, # 允许跨域
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router) # 注册业务路由
    return app


app = create_app()
