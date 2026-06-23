from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from common.exceptions import BusinessException


class JWTSettings(Protocol):
    """JWT 配置协议。

    用途：
        约束 JWT 编码、解码所需配置，避免公共包依赖具体子应用配置类。
    参数：
        无构造参数。
    返回值：
        协议类型本身，仅用于类型检查。
    """

    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int


@dataclass(frozen=True)
class AccessToken:
    """访问 token 结果。

    用途：
        承载生成后的 JWT、jti 和过期时间，方便业务层写 Redis 登录态。
    参数：
        access_token：JWT 字符串。
        jti：本次 token 的唯一 ID。
        expires_at：过期时间戳。
        expires_in：剩余有效秒数。
    返回值：
        dataclass 实例。
    """

    access_token: str
    jti: str
    expires_at: int
    expires_in: int


def hash_password(password: str) -> str:
    """生成密码哈希。

    用途：
        将用户明文密码转换为不可逆哈希值，用于写入 sys_user.password_hash。
    参数：
        password：用户输入的明文密码。
    返回值：
        bcrypt 密码哈希字符串。
    """

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise BusinessException(code=40000, msg="密码长度不能超过72字节")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码。

    用途：
        登录时校验用户输入的明文密码是否匹配数据库中的密码哈希。
    参数：
        password：用户输入的明文密码。
        password_hash：数据库中保存的密码哈希。
    返回值：
        匹配返回 True，否则返回 False。
    """

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72: # bcrypt 只能处理最长 72 字节的密码，超过部分会被忽略，可能导致安全问题，因此直接返回 False
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


def create_access_token(settings: JWTSettings, payload: dict[str, Any]) -> AccessToken:
    """创建访问 token。

    用途：
        生成带 user_id、username、role_id、token_version、jti、exp 的 JWT。
    参数：
        settings：JWT 配置对象。
        payload：需要写入 JWT 的业务字段。
    返回值：
        AccessToken 实例，包含 token 字符串和过期信息。
    """

    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes) # 从配置中读取过期时间，单位为分钟
    expires_at = now + expires_delta
    expires_at_timestamp = int(expires_at.timestamp())
    jti = uuid4().hex  # 生成 jti，确保每个 token 都有唯一 ID，方便后续单点登录和黑名单校验

    claims = payload.copy()
    claims.update(
        {
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": expires_at_timestamp,
        }
    )
    access_token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return AccessToken(
        access_token=access_token,
        jti=jti,
        expires_at=expires_at_timestamp, # 过期时间戳，方便 Redis 登录态设置过期
        expires_in=int(expires_delta.total_seconds()),
    )


def decode_access_token(settings: JWTSettings, token: str) -> dict[str, Any]:
    """解析访问 token。

    用途：
        校验 JWT 签名和过期时间，并返回 token 中的业务载荷。
    参数：
        settings：JWT 配置对象。
        token：请求头中的 Bearer token。
    返回值：
        解码后的 JWT 载荷字典。
    """

    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise BusinessException(code=40100, msg="登录凭证无效") from exc


def digest_token(token: str) -> str:
    """生成 token 摘要。

    用途：
        Redis 登录态只保存 token 摘要，不保存完整 JWT，降低缓存泄露后的影响。
    参数：
        token：完整 JWT 字符串。
    返回值：
        SHA256 摘要字符串。
    """

    return sha256(token.encode("utf-8")).hexdigest()
