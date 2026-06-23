import sys
from pathlib import Path
from typing import Protocol

from loguru import logger


class LoggerSettings(Protocol):
    """日志配置协议。

    用途：
        约束初始化日志时需要读取的配置字段，避免公共包依赖具体子应用配置类。
    参数：
        无构造参数。
    返回值：
        协议类型本身，仅用于类型检查。
    """

    log_level: str # 日志等级："DEBUG"/"INFO"/"WARNING"/"ERROR"/"CRITICAL"
    log_file_enabled: bool # 是否开启文件落盘日志 True/False
    log_dir: str # 日志文件夹路径字符串


def configure_logger(settings: LoggerSettings) -> None:
    """初始化 loguru 日志。

    用途：
        统一配置控制台日志和可选文件日志，保证服务启动后日志格式一致。
    参数：
        settings：包含日志级别、日志目录和文件日志开关的配置对象。
    返回值：
        无返回值，函数会修改全局 logger 配置。
    """

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        enqueue=True, # 异步写入
        backtrace=False, # 堆栈跟踪
        diagnose=False, # 诊断
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
    )

    if settings.log_file_enabled:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "app.log",
            level=settings.log_level,
            rotation="100 MB", # 日志文件大小限制
            retention="14 days", # 日志文件保存时长
            encoding="utf-8",
            enqueue=True, # 异步写入
            backtrace=False, # 堆栈跟踪
            diagnose=False, # 诊断
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
        )
