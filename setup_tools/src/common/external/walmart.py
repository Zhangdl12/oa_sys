from common.external.base import BaseExternalClient


class WalmartClient(BaseExternalClient):
    """Walmart Marketplace 客户端占位实现。

    用途：
        后续封装 access token、公共请求头、shipping update 和错误检查。
    参数：
        继承 BaseExternalClient 的初始化参数。
    返回值：
        Walmart 客户端实例。
    """
