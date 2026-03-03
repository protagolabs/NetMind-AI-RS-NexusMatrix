"""
@file_name: main.py
@author: Bin Liang
@date: 2026-03-03
@description: 服务入口点

提供 CLI 启动方式，支持通过命令行参数配置服务。
"""

import sys
import uvicorn
from loguru import logger

from nexus_matrix.config import get_settings


def setup_logging(log_level: str = "INFO") -> None:
    """配置 loguru 日志。"""
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    # 文件日志
    logger.add(
        "logs/nexus_matrix_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        level=log_level,
    )


def main() -> None:
    """服务入口函数。"""
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info(f"启动 NexusMatrix 服务: {settings.host}:{settings.port}")

    uvicorn.run(
        "nexus_matrix.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
