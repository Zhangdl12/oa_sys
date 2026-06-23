import json
from typing import Any

import httpx

from common.exceptions import FeishuException
from common.external.base import BaseExternalClient

FEISHU_TOKEN_KEY_TEMPLATE = "oa:external:feishu:token:{app_name}"
TENANT_ACCESS_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_PATH = "/open-apis/im/v1/messages"
TOKEN_TTL_SAFETY_SECONDS = 300
MIN_TOKEN_TTL_SECONDS = 60


class FeishuClient(BaseExternalClient):
    """飞书开放平台客户端。

    用途：
        封装 tenant_access_token 获取、缓存和错误码检查。
    参数：
        继承 BaseExternalClient 的初始化参数。
    返回值：
        飞书客户端实例。
    """

    async def get_tenant_access_token(self, app_id: str, app_secret: str) -> str:
        """获取飞书 tenant_access_token。

        用途：
            使用自建应用 app_id 和 app_secret 调用飞书 token 接口。
        参数：
            app_id：飞书自建应用 App ID。
            app_secret：飞书自建应用 App Secret。
        返回值：
            飞书 tenant_access_token 字符串。
        """

        payload = await self._request_tenant_access_token(app_id, app_secret)
        return str(payload["tenant_access_token"])

    async def get_cached_tenant_access_token(
        self,
        redis_client: Any,
        app_name: str,
        app_id: str,
        app_secret: str,
    ) -> str:
        """获取带 Redis 缓存的飞书 tenant_access_token。

        用途：
            优先读取 Redis 缓存；未命中时调用飞书接口并按 expire 设置缓存 TTL。
        参数：
            redis_client：Redis 异步客户端。
            app_name：当前应用名称，用于区分缓存 key。
            app_id：飞书自建应用 App ID。
            app_secret：飞书自建应用 App Secret。
        返回值：
            可用的 tenant_access_token。
        """

        cache_key = FEISHU_TOKEN_KEY_TEMPLATE.format(app_name=app_name)
        cached_value = await redis_client.get(cache_key)
        if cached_value:
            try:
                cached_payload = json.loads(cached_value)
            except json.JSONDecodeError:
                cached_payload = {}
            cached_token = cached_payload.get("tenant_access_token")
            if cached_token:
                return str(cached_token)

        payload = await self._request_tenant_access_token(app_id, app_secret)
        token = str(payload["tenant_access_token"])
        expire = int(payload.get("expire") or 0)
        ttl = max(expire - TOKEN_TTL_SAFETY_SECONDS, MIN_TOKEN_TTL_SECONDS)
        await redis_client.set(
            cache_key,
            json.dumps(
                {
                    "tenant_access_token": token,
                    "expire": expire,
                },
                ensure_ascii=False,
            ),
            ex=ttl,
        )
        return token

    async def _request_tenant_access_token(
        self,
        app_id: str,
        app_secret: str,
    ) -> dict[str, Any]:
        """请求飞书 tenant_access_token 原始响应。"""

        try:
            response = await self.http_client.post(
                self.build_url(TENANT_ACCESS_TOKEN_PATH),
                json={
                    "app_id": app_id,
                    "app_secret": app_secret,
                },
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FeishuException(msg="飞书 token 接口请求失败", data={"error": str(exc)}) from exc
        except ValueError as exc:
            raise FeishuException(msg="飞书 token 响应不是合法 JSON") from exc

        if not isinstance(payload, dict):
            raise FeishuException(msg="飞书 token 响应格式错误", data=payload)
        if payload.get("code") != 0:
            msg = str(payload.get("msg") or "飞书 token 获取失败")
            raise FeishuException(msg=msg, data=payload)
        if not payload.get("tenant_access_token"):
            raise FeishuException(msg="飞书 token 响应缺少 tenant_access_token", data=payload)
        return payload

    async def send_text_message(
        self,
        tenant_access_token: str,
        receive_id_type: str,
        receive_id: str,
        text: str,
    ) -> dict[str, Any]:
        """发送飞书文本消息。

        用途：
            使用 tenant_access_token 向指定 open_id 发送文本消息。
        参数：
            tenant_access_token：飞书租户访问 token。
            receive_id_type：飞书接收人 ID 类型，支持 open_id 或 chat_id。
            receive_id：飞书用户 open_id。
            text：文本消息内容。
        返回值：
            飞书发送消息接口响应。
        """

        try:
            response = await self.http_client.post(
                self.build_url(SEND_MESSAGE_PATH),
                params={"receive_id_type": receive_id_type},
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
                headers={
                    "Authorization": f"Bearer {tenant_access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FeishuException(msg="飞书消息发送接口请求失败", data={"error": str(exc)}) from exc
        except ValueError as exc:
            raise FeishuException(msg="飞书消息发送响应不是合法 JSON") from exc

        if not isinstance(payload, dict):
            raise FeishuException(msg="飞书消息发送响应格式错误", data=payload)
        if payload.get("code") != 0:
            msg = str(payload.get("msg") or "飞书消息发送失败")
            raise FeishuException(msg=msg, data=payload)
        return payload

    async def send_card_message(
        self,
        tenant_access_token: str,
        receive_id_type: str,
        receive_id: str,
        card: dict[str, Any],
    ) -> dict[str, Any]:
        """发送飞书消息卡片。"""

        try:
            response = await self.http_client.post(
                self.build_url(SEND_MESSAGE_PATH),
                params={"receive_id_type": receive_id_type},
                json={
                    "receive_id": receive_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
                headers={
                    "Authorization": f"Bearer {tenant_access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FeishuException(msg="飞书消息发送接口请求失败", data={"error": str(exc)}) from exc
        except ValueError as exc:
            raise FeishuException(msg="飞书消息发送响应不是合法 JSON") from exc

        if not isinstance(payload, dict):
            raise FeishuException(msg="飞书消息发送响应格式错误", data=payload)
        if payload.get("code") != 0:
            msg = str(payload.get("msg") or "飞书消息发送失败")
            raise FeishuException(msg=msg, data=payload)
        return payload
