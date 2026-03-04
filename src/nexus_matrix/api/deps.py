"""
@file_name: deps.py
@author: Bin Liang
@date: 2026-03-03
@description: FastAPI 依赖注入

集中管理所有服务的实例化和生命周期，
提供 FastAPI Depends() 可用的依赖函数。
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from nio import AsyncClient

from nexus_matrix.config import Settings, get_settings
from nexus_matrix.core.auth_service import AuthService
from nexus_matrix.core.matrix_client_manager import MatrixClientManager
from nexus_matrix.core.message_service import MessageService
from nexus_matrix.core.room_service import RoomService
from nexus_matrix.core.sync_service import SyncService
from nexus_matrix.models.auth import TokenInfo
from nexus_matrix.registry.registry_service import RegistryService
from nexus_matrix.registry.search_service import SearchService
from nexus_matrix.storage.database import Database
from nexus_matrix.storage.repositories.agent_repo import AgentRepository
from nexus_matrix.storage.repositories.api_key_repo import ApiKeyRepository
from nexus_matrix.storage.repositories.feedback_repo import FeedbackRepository
from nexus_matrix.utils.embedding import EmbeddingService


class ServiceContainer:
    """服务容器（单例）。

    集中管理所有服务实例的生命周期，
    在应用启动时初始化，关闭时清理。
    """

    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.db: Optional[Database] = None
        self.client_manager: Optional[MatrixClientManager] = None
        self.agent_repo: Optional[AgentRepository] = None
        self.api_key_repo: Optional[ApiKeyRepository] = None
        self.auth_service: Optional[AuthService] = None
        self.room_service: Optional[RoomService] = None
        self.message_service: Optional[MessageService] = None
        self.sync_service: Optional[SyncService] = None
        self.registry_service: Optional[RegistryService] = None
        self.search_service: Optional[SearchService] = None
        self.embedding_service: Optional[EmbeddingService] = None
        self.feedback_repo: Optional[FeedbackRepository] = None

    async def init(self, settings: Optional[Settings] = None) -> None:
        """初始化所有服务。"""
        self.settings = settings or get_settings()

        # 数据库
        self.db = Database(self.settings.database_path)
        await self.db.connect()

        # Repository
        self.agent_repo = AgentRepository(self.db)
        self.api_key_repo = ApiKeyRepository(self.db)
        self.feedback_repo = FeedbackRepository(self.db)

        # Matrix 客户端管理器
        self.client_manager = MatrixClientManager(self.settings)

        # Embedding 服务（通过 OpenAI API）
        self.embedding_service = EmbeddingService(
            model=self.settings.embedding_model,
            api_key=self.settings.openai_api_key,
        )

        # 核心服务
        self.auth_service = AuthService(
            self.settings, self.client_manager, self.agent_repo, self.api_key_repo
        )
        self.room_service = RoomService(self.client_manager)
        self.message_service = MessageService()
        self.sync_service = SyncService(self.db)

        # 注册中心
        self.registry_service = RegistryService(
            self.settings, self.auth_service, self.agent_repo, self.embedding_service
        )
        self.search_service = SearchService(self.agent_repo, self.embedding_service)

    async def close(self) -> None:
        """清理所有服务资源。"""
        if self.client_manager:
            await self.client_manager.close_all()
        if self.db:
            await self.db.disconnect()


# 全局服务容器单例
container = ServiceContainer()


# ── FastAPI 依赖函数 ──

def get_container() -> ServiceContainer:
    """获取服务容器。"""
    return container


def get_auth_service() -> AuthService:
    """获取认证服务。"""
    return container.auth_service


def get_room_service() -> RoomService:
    """获取房间服务。"""
    return container.room_service


def get_message_service() -> MessageService:
    """获取消息服务。"""
    return container.message_service


def get_sync_service() -> SyncService:
    """获取同步服务。"""
    return container.sync_service


def get_registry_service() -> RegistryService:
    """获取注册服务。"""
    return container.registry_service


def get_search_service() -> SearchService:
    """获取搜索服务。"""
    return container.search_service


def get_feedback_repo() -> FeedbackRepository:
    """获取反馈数据仓库。"""
    return container.feedback_repo


async def get_current_user(
    x_api_key: str = Header(..., description="NexusMatrix API Key"),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenInfo:
    """校验 API Key 并返回当前用户信息。

    此依赖注入函数用于保护需要认证的 API 端点。

    Args:
        x_api_key: 请求头中的 API Key。
        auth_service: 认证服务。

    Returns:
        当前用户的 Token 信息。

    Raises:
        HTTPException: API Key 无效时返回 401。
    """
    token_info = await auth_service.validate_api_key(x_api_key)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )
    return token_info


async def get_matrix_client(
    current_user: TokenInfo = Depends(get_current_user),
) -> AsyncClient:
    """获取当前用户的 Matrix 客户端。

    始终从数据库获取最新 token，通过 create_client 创建或更新客户端。
    这确保了即使 Agent 重新注册导致 token 变化，也能自动同步。

    Args:
        current_user: 当前认证用户信息。

    Returns:
        已认证的 AsyncClient 实例。

    Raises:
        HTTPException: 无法获取客户端时返回 500。
    """
    # 始终从 DB 获取最新 token，确保 token 不过期
    if current_user.agent_id:
        key_record = await container.api_key_repo.get_by_agent_id(current_user.agent_id)
        if key_record:
            return await container.client_manager.create_client(
                user_id=current_user.user_id,
                access_token=key_record["access_token"],
                device_id=key_record.get("device_id", ""),
            )

    # 回退：尝试从池中获取已有客户端
    client = await container.client_manager.get_client(current_user.user_id)
    if client:
        return client

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to create Matrix client for this user",
    )
