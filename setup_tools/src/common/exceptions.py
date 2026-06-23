from typing import Any


class BusinessException(Exception):
    """业务异常基类。

    用途：
        表示可预期的业务错误，例如未登录、无权限、数据不存在。
    参数：
        code：业务错误码。
        msg：错误提示信息。
        data：额外错误详情，默认不返回。
    返回值：
        异常对象本身，由统一异常处理器转换为 JSON 响应。
    """

    def __init__(self, code: int = 40000, msg: str = "业务处理失败", data: Any = None) -> None:
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(msg)


class ExternalApiException(BusinessException):
    """外部平台异常基类。

    用途：
        表示飞书、七牛云、Walmart、领星等外部平台调用失败。
    参数：
        code：业务错误码，默认使用外部平台错误码段。
        msg：错误提示信息。
        data：外部平台返回的关键错误详情。
    返回值：
        异常对象本身，由统一异常处理器转换为 JSON 响应。
    """

    def __init__(
        self,
        msg: str = "外部平台调用失败",
        data: Any = None,
        code: int = 60000,
    ) -> None:
        super().__init__(code=code, msg=msg, data=data)


class FeishuException(ExternalApiException):
    """飞书平台异常。"""


class QiniuException(ExternalApiException):
    """七牛云平台异常。"""


class WalmartException(ExternalApiException):
    """Walmart 平台异常。"""


class LingxingException(ExternalApiException):
    """领星平台异常。"""
