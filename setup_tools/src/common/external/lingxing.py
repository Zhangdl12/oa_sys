from common.external.base import BaseExternalClient


class LingxingClient(BaseExternalClient):
    """领星开放平台客户端占位实现。

    用途：
        后续封装 access_token、refresh_token、签名、限流和错误码转换。
    参数：
        继承 BaseExternalClient 的初始化参数。
    返回值：
        领星客户端实例。
    """
