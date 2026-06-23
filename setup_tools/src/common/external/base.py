from typing import Any

import httpx

from common.exceptions import ExternalApiException


class BaseExternalClient:
    """外部平台客户端基类。

    用途：
        复用外部平台调用的基础能力，例如基础地址、HTTP 客户端和响应错误检查。
    参数：
        http_client：全局复用的 httpx.AsyncClient。
        base_url：外部平台 API 基础地址。
    返回值：
        外部平台客户端实例。
    """

    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")

    def build_url(self, path: str) -> str:
        """拼接完整请求地址。

        用途：
            将平台基础域名和接口路径拼成完整 URL。
        参数：
            path：接口路径，允许带或不带开头斜杠。
        返回值：
            完整接口地址。
        """

        return f"{self.base_url}/{path.lstrip('/')}"

    def check_response_code(self, payload: dict[str, Any], success_codes: set[int | str]) -> None:
        """检查外部平台响应码。

        用途：
            将外部平台非成功响应统一转换为 ExternalApiException。
        参数：
            payload：外部平台返回的 JSON 字典。
            success_codes：当前平台认为成功的 code 集合。
        返回值：
            无返回值；失败时直接抛出异常。
        """

        code = payload.get("code")
        if code not in success_codes:
            msg = str(payload.get("msg") or payload.get("message") or "外部平台调用失败")
            raise ExternalApiException(msg=msg, data=payload)
