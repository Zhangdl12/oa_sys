from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """OA 管理后台配置。

    用途：
        从 .env.shared、子应用 .env 和系统环境变量中读取服务配置。
    参数：
        所有字段均由 pydantic-settings 自动读取，不需要手动传参。
    返回值：
        配置对象实例，供应用启动、依赖注入和公共基础包使用。
    """

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env.shared", APP_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "oa_admin"
    app_env: str = "local"
    debug: bool = Field(default=True, validation_alias="APP_DEBUG") 
    api_prefix: str = "/v1"
    docs_enabled: bool = True
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])

    log_level: str = "INFO"
    log_file_enabled: bool = False
    log_dir: str = "logs"

    mysql_enabled: bool = False
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "oa_user"
    mysql_password: str = "oa_password"
    mysql_database: str = "oa"
    mysql_min_size: int = 1
    mysql_max_size: int = 10

    redis_enabled: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_password: str = ""
    rbac_cache_ttl_seconds: int = 1800 #这是 30 分钟，RBAC 权限缓存过期时间

    http_timeout_seconds: int = 15
    http_max_connections: int = 100
    http_max_keepalive_connections: int = 20

    feishu_enabled: bool = False
    feishu_base_url: str = "https://open.feishu.cn"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    user_create_notify_enabled: bool = False
    user_create_notify_receive_id_type: Literal["open_id", "chat_id", "user_id"] = "user_id"
    user_create_notify_receive_id: str = ""
    permission_notify_enabled: bool = False
    permission_notify_receive_id_type: Literal["open_id", "chat_id", "user_id"] = "user_id"
    permission_notify_receive_id: str = ""

    jwt_secret_key: str = "change-me-in-real-env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120


@lru_cache # 缓存配置对象
def get_settings() -> Settings:
    """获取全局配置单例。

    用途：
        避免每次依赖注入都重复读取环境变量和解析配置文件。
    参数：
        无。
    返回值：
        Settings 配置对象。
    """

    return Settings()
