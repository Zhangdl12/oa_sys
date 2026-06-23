from common.response import success
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def get_health(request: Request) -> dict:
    """获取服务健康状态。

    用途：
        提供最小可用健康检查接口，用于本地开发、容器探活和部署验证。
    参数：
        request：当前 HTTP 请求对象，用于读取 app.state 中的应用配置。
    返回值：
        统一响应结构，data 中包含应用名、环境和资源初始化状态。
    """

    settings = request.app.state.settings
    data = {
        "status": "ok",
        "app_name": settings.app_name,
        "env": settings.app_env,
        "mysql_enabled": settings.mysql_enabled,
        "mysql_ready": request.app.state.mysql_pool is not None,
        "redis_enabled": settings.redis_enabled,
        "redis_ready": request.app.state.redis_client is not None,
        "http_client_ready": request.app.state.http_client is not None,
    }
    return success(data)
