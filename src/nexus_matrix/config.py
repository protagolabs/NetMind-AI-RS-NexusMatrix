"""
@file_name: config.py
@author: Bin Liang
@date: 2026-03-03
@description: 全局配置管理

使用 pydantic-settings 从环境变量和 .env 文件加载配置。
所有配置项都有合理的默认值，支持开发和生产环境切换。
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 将 .env 加载到系统环境变量，供非 NEXUS_ 前缀字段读取
load_dotenv()


class Settings(BaseSettings):
    """全局配置，优先从环境变量读取，回退到 .env 文件。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NEXUS_",
        extra="ignore",
        case_sensitive=False,
    )

    # ── 服务配置 ──
    host: str = "0.0.0.0"
    port: int = 8953
    debug: bool = False
    log_level: str = "INFO"

    # ── Matrix Homeserver 配置 ──
    matrix_homeserver_url: str = "http://localhost:8008"
    matrix_server_name: str = "localhost"
    # Synapse 共享注册密钥，用于程序化创建用户
    matrix_registration_secret: Optional[str] = None
    # 管理员账户凭据（服务启动时自动创建）
    matrix_admin_user: str = "nexus_admin"
    matrix_admin_password: str = "nexus_admin_password"

    # ── 数据库配置 ──
    database_path: str = "data/nexus_matrix.db"

    # ── 安全配置 ──
    # API Key 签名密钥
    secret_key: str = "nexus-matrix-secret-change-me-in-production"
    # API Key 过期时间（天），0 表示永不过期
    api_key_expire_days: int = 0

    # ── OpenAI 配置（不带 NEXUS_ 前缀，直接读 OPENAI_API_KEY）──
    openai_api_key: Optional[str] = None
    # 嵌入模型配置
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    @model_validator(mode="after")
    def _resolve_openai_key(self) -> "Settings":
        """如果 NEXUS_OPENAI_API_KEY 未设置，回退到 OPENAI_API_KEY 环境变量。"""
        if not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        return self

    # ── 同步配置 ──
    # 后台同步轮询间隔（毫秒）
    sync_timeout_ms: int = 30000
    # 最大缓存消息数
    max_cached_messages: int = 1000

    @property
    def database_dir(self) -> Path:
        """数据库文件所在目录。"""
        return Path(self.database_path).parent

    @property
    def matrix_admin_mxid(self) -> str:
        """管理员的完整 Matrix ID。"""
        return f"@{self.matrix_admin_user}:{self.matrix_server_name}"


@lru_cache()
def get_settings() -> Settings:
    """获取全局配置单例。"""
    return Settings()
