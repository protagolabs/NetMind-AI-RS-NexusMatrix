"""
@file_name: matrix_client_manager.py
@author: Bin Liang
@date: 2026-03-03
@description: Matrix 客户端管理器

管理 matrix-nio AsyncClient 实例的生命周期，
为每个已注册 Agent 维护一个持久化的客户端连接。
支持连接池、自动重连、优雅关闭。
"""

import asyncio
from typing import Dict, Optional

from nio import AsyncClient, AsyncClientConfig, LoginResponse
from loguru import logger

from nexus_matrix.config import Settings


class MatrixClientManager:
    """Matrix 客户端连接池管理器。

    核心职责：
    - 为每个 Agent 创建和管理 AsyncClient 实例
    - 提供管理员客户端（用于服务端操作）
    - 处理连接生命周期（创建、登录、恢复、关闭）
    """

    def __init__(self, settings: Settings) -> None:
        """初始化客户端管理器。

        Args:
            settings: 全局配置。
        """
        self._settings = settings
        self._homeserver_url = settings.matrix_homeserver_url
        self._server_name = settings.matrix_server_name
        # Agent 客户端池: matrix_user_id -> AsyncClient
        self._clients: Dict[str, AsyncClient] = {}
        # 管理员客户端
        self._admin_client: Optional[AsyncClient] = None
        # 保护并发访问的锁
        self._lock = asyncio.Lock()

    @property
    def admin_client(self) -> Optional[AsyncClient]:
        """获取管理员客户端。"""
        return self._admin_client

    @property
    def homeserver_url(self) -> str:
        """Homeserver URL。"""
        return self._homeserver_url

    @property
    def server_name(self) -> str:
        """服务器域名。"""
        return self._server_name

    async def init_admin_client(self) -> AsyncClient:
        """初始化管理员客户端。

        使用配置中的管理员凭据登录，
        管理员客户端用于程序化注册用户等服务端操作。

        Returns:
            已登录的管理员 AsyncClient。
        """
        config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
        )
        client = AsyncClient(
            self._homeserver_url,
            user=f"@{self._settings.matrix_admin_user}:{self._server_name}",
            config=config,
        )

        response = await client.login(self._settings.matrix_admin_password)
        if isinstance(response, LoginResponse):
            self._admin_client = client
            logger.info(f"管理员客户端已登录: {response.user_id}")
            return client
        else:
            logger.error(f"管理员登录失败: {response}")
            raise RuntimeError(f"Admin login failed: {response}")

    async def create_client(
        self,
        user_id: str,
        access_token: str,
        device_id: str = "",
    ) -> AsyncClient:
        """为已注册的 Agent 创建或更新客户端实例。

        使用已有的 access_token 恢复登录状态，无需重新认证。
        如果客户端已存在但 token 不同（如重新注册后），会更新 token。

        Args:
            user_id: 完整 Matrix User ID (e.g., @bot:server)。
            access_token: Matrix access token。
            device_id: 设备 ID。

        Returns:
            已认证的 AsyncClient 实例。
        """
        async with self._lock:
            existing = self._clients.get(user_id)
            if existing:
                # 关键修复：如果 token 变化（重新注册/登录），更新客户端
                if existing.access_token == access_token:
                    return existing
                logger.info(f"客户端 token 已更新: {user_id}")
                existing.access_token = access_token
                existing.device_id = device_id
                return existing

            config = AsyncClientConfig(
                max_limit_exceeded=0,
                max_timeouts=0,
            )
            client = AsyncClient(
                self._homeserver_url,
                user=user_id,
                config=config,
            )
            # 通过 token 恢复登录状态
            client.access_token = access_token
            client.user_id = user_id
            client.device_id = device_id

            self._clients[user_id] = client
            logger.debug(f"客户端已创建: {user_id}")
            return client

    async def get_client(self, user_id: str) -> Optional[AsyncClient]:
        """获取已存在的客户端实例。

        Args:
            user_id: Matrix User ID。

        Returns:
            AsyncClient 实例，若不存在返回 None。
        """
        return self._clients.get(user_id)

    async def remove_client(self, user_id: str) -> None:
        """移除并关闭客户端实例。

        Args:
            user_id: Matrix User ID。
        """
        async with self._lock:
            client = self._clients.pop(user_id, None)
            if client:
                await client.close()
                logger.debug(f"客户端已关闭: {user_id}")

    async def login_with_password(
        self, username: str, password: str
    ) -> tuple:
        """使用密码登录 Matrix（用于首次登录）。

        Args:
            username: 用户名（localpart 或完整 MXID）。
            password: 密码。

        Returns:
            (user_id, access_token, device_id) 元组。

        Raises:
            RuntimeError: 登录失败。
        """
        # 构造完整的 MXID
        if not username.startswith("@"):
            user_id = f"@{username}:{self._server_name}"
        else:
            user_id = username

        config = AsyncClientConfig(max_limit_exceeded=0, max_timeouts=0)
        client = AsyncClient(self._homeserver_url, user=user_id, config=config)

        try:
            response = await client.login(password)
            if isinstance(response, LoginResponse):
                # 保存到连接池
                async with self._lock:
                    self._clients[response.user_id] = client
                return response.user_id, response.access_token, response.device_id
            else:
                await client.close()
                raise RuntimeError(f"Login failed: {response}")
        except Exception:
            await client.close()
            raise

    async def close_all(self) -> None:
        """关闭所有客户端连接（服务关闭时调用）。"""
        async with self._lock:
            for user_id, client in self._clients.items():
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"关闭客户端 {user_id} 时出错: {e}")
            self._clients.clear()

            if self._admin_client:
                try:
                    await self._admin_client.close()
                except Exception as e:
                    logger.warning(f"关闭管理员客户端时出错: {e}")
                self._admin_client = None

        logger.info("所有 Matrix 客户端已关闭")
