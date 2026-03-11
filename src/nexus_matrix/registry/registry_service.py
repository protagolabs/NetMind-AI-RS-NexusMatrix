"""
@file_name: registry_service.py
@author: Bin Liang
@date: 2026-03-03
@description: Agent 注册服务

处理 Agent 的注册、档案更新、状态管理等核心逻辑。
注册流程：
1. 在 Matrix homeserver 创建用户
2. 生成 embedding（用于语义搜索）
3. 存储 Agent 档案到数据库
4. 生成并返回 API Key
"""

from typing import List, Optional

from loguru import logger

from nexus_matrix.config import Settings
from nexus_matrix.core.auth_service import AuthService
from nexus_matrix.models.auth import RegisterResponse
from nexus_matrix.models.registry import (
    AgentProfile,
    AgentRegistration,
    AgentStatus,
)
from nexus_matrix.storage.repositories.agent_repo import AgentRepository
from nexus_matrix.utils.embedding import EmbeddingService
from nexus_matrix.utils.security import generate_api_key, generate_id, hash_api_key


class RegistryService:
    """Agent 注册服务。

    管理 Agent 的完整生命周期：注册、更新、停用、删除。
    """

    def __init__(
        self,
        settings: Settings,
        auth_service: AuthService,
        agent_repo: AgentRepository,
        embedding_service: EmbeddingService,
    ) -> None:
        self._settings = settings
        self._auth_service = auth_service
        self._agent_repo = agent_repo
        self._embedding_service = embedding_service

    async def register(self, registration: AgentRegistration) -> dict:
        """注册新 Agent（幂等操作）。

        完整注册流程：
        1. 生成唯一用户名
        2. 在 Matrix 创建用户（已存在则重置密码并登录）
        3. 检查 Agent 是否已在本地注册，若是则走重新激活流程
        4. 生成描述的 embedding
        5. 存储 Agent 档案
        6. 生成并返回 API Key

        Args:
            registration: Agent 注册信息。

        Returns:
            包含 agent_profile 和 register_response 的字典。
        """
        # 如果提供了 preferred_username 则优先使用，否则从 agent_name 自动生成
        if registration.preferred_username:
            username = self._sanitize_username(registration.preferred_username)
        else:
            username = self._sanitize_username(registration.agent_name)
        password = generate_id("pwd", length=16)

        # Step 1: 在 Matrix 创建用户（已存在则自动重置密码并登录）
        matrix_result = await self._auth_service.register_matrix_user(
            username=username,
            password=password,
            display_name=registration.agent_name,
        )

        user_id = matrix_result["user_id"]
        access_token = matrix_result["access_token"]
        device_id = matrix_result["device_id"]

        # Step 2: 检查是否已注册过（幂等处理）
        existing_profile = await self._agent_repo.get_by_matrix_user_id(user_id)
        if existing_profile:
            logger.info(
                f"Agent 已存在，重新激活: {existing_profile.agent_id} "
                f"({existing_profile.agent_name}) -> {user_id}"
            )
            # 更新 Agent 状态为 ACTIVE，刷新描述/能力
            updates = {
                "status": AgentStatus.ACTIVE.value,
                "description": registration.description,
                "capabilities": registration.capabilities,
            }
            if registration.webhook_url:
                updates["webhook_url"] = registration.webhook_url
            await self._agent_repo.update(existing_profile.agent_id, updates)

            # 重新生成 embedding
            try:
                embedding_text = self._build_embedding_text(registration)
                embedding = self._embedding_service.encode(embedding_text)
                await self._agent_repo.update_embedding(
                    existing_profile.agent_id,
                    self._embedding_service.to_bytes(embedding),
                )
            except Exception as e:
                logger.warning(f"重新生成 embedding 失败: {e}")

            # 生成新的 API Key
            api_key = generate_api_key()
            key_id = generate_id("key")
            await self._auth_service._api_key_repo.create(
                key_id=key_id,
                api_key_hash=hash_api_key(api_key),
                agent_id=existing_profile.agent_id,
                matrix_user_id=user_id,
                access_token=access_token,
                device_id=device_id,
            )

            # 确保客户端池有连接
            await self._auth_service._client_manager.create_client(
                user_id, access_token, device_id
            )

            refreshed_profile = await self._agent_repo.get_by_id(existing_profile.agent_id)
            return {
                "agent_profile": refreshed_profile,
                "api_key": api_key,
                "matrix_user_id": user_id,
                "matrix_access_token": access_token,
            }

        # ---- 以下为首次注册流程 ----
        agent_id = generate_id("agt")

        # Step 3: 生成 embedding
        embedding_text = self._build_embedding_text(registration)
        try:
            embedding = self._embedding_service.encode(embedding_text)
            embedding_bytes = self._embedding_service.to_bytes(embedding)
        except Exception as e:
            logger.warning(f"生成 embedding 失败（语义搜索不可用）: {e}")
            embedding_bytes = None

        # Step 4: 先存储 Agent 档案（agents 表），再存 API Key（api_keys 表）
        # 修复 FK 约束：api_keys.agent_id 引用 agents.agent_id，必须先插 agents
        profile = await self._agent_repo.create(
            agent_id=agent_id,
            agent_name=registration.agent_name,
            matrix_user_id=user_id,
            description=registration.description,
            capabilities=registration.capabilities,
            metadata=registration.metadata,
            webhook_url=registration.webhook_url,
            owner=registration.owner,
            embedding=embedding_bytes,
        )

        # Step 5: 生成并存储 API Key
        api_key = generate_api_key()
        key_id = generate_id("key")
        await self._auth_service._api_key_repo.create(
            key_id=key_id,
            api_key_hash=hash_api_key(api_key),
            agent_id=agent_id,
            matrix_user_id=user_id,
            access_token=access_token,
            device_id=device_id,
        )

        # Step 6: 在客户端池中创建连接
        await self._auth_service._client_manager.create_client(
            user_id, access_token, device_id
        )

        logger.info(
            f"Agent 已注册: {agent_id} ({registration.agent_name}) "
            f"-> {user_id}"
        )

        return {
            "agent_profile": profile,
            "api_key": api_key,
            "matrix_user_id": user_id,
            "matrix_access_token": access_token,
        }

    async def update_profile(
        self, agent_id: str, updates: dict
    ) -> Optional[AgentProfile]:
        """更新 Agent 档案。

        如果更新了描述或能力标签，会重新生成 embedding。

        Args:
            agent_id: Agent ID。
            updates: 要更新的字段。

        Returns:
            更新后的 Agent 档案。
        """
        profile = await self._agent_repo.get_by_id(agent_id)
        if not profile:
            return None

        # 如果描述或能力变化，重新生成 embedding
        needs_reembed = "description" in updates or "capabilities" in updates
        result = await self._agent_repo.update(agent_id, updates)

        if needs_reembed and result:
            try:
                reg = AgentRegistration(
                    agent_name=result.agent_name,
                    description=result.description,
                    capabilities=result.capabilities,
                )
                text = self._build_embedding_text(reg)
                embedding = self._embedding_service.encode(text)
                await self._agent_repo.update_embedding(
                    agent_id, self._embedding_service.to_bytes(embedding)
                )
            except Exception as e:
                logger.warning(f"重新生成 embedding 失败: {e}")

        return result

    async def deactivate(self, agent_id: str) -> bool:
        """停用 Agent。"""
        result = await self._agent_repo.update(
            agent_id, {"status": AgentStatus.INACTIVE.value}
        )
        return result is not None

    async def activate(self, agent_id: str) -> bool:
        """激活 Agent。"""
        result = await self._agent_repo.update(
            agent_id, {"status": AgentStatus.ACTIVE.value}
        )
        return result is not None

    async def get_profile(self, agent_id: str) -> Optional[AgentProfile]:
        """获取 Agent 档案。"""
        return await self._agent_repo.get_by_id(agent_id)

    async def get_profile_by_matrix_id(self, matrix_user_id: str) -> Optional[AgentProfile]:
        """根据 Matrix User ID 获取 Agent 档案。"""
        return await self._agent_repo.get_by_matrix_user_id(matrix_user_id)

    async def list_agents(
        self, limit: int = 100, offset: int = 0
    ) -> List[AgentProfile]:
        """列出所有活跃 Agent。"""
        return await self._agent_repo.list_active(limit=limit, offset=offset)

    async def delete(self, agent_id: str) -> bool:
        """删除 Agent（级联删除所有关联数据）。"""
        return await self._agent_repo.delete(agent_id)

    @staticmethod
    def _sanitize_username(name: str) -> str:
        """将 Agent 名称转为合法的 Matrix 用户名。

        Matrix 用户名只允许小写字母、数字、点、连字符、下划线。
        """
        import re
        # 转小写，替换空格为下划线
        username = name.lower().replace(" ", "_")
        # 移除非法字符
        username = re.sub(r"[^a-z0-9._\-]", "", username)
        # 确保不为空且长度合适
        if not username:
            username = generate_id("agent", length=8)
        return username[:50]

    @staticmethod
    def _build_embedding_text(registration: AgentRegistration) -> str:
        """构造用于 embedding 的文本。

        将 Agent 的名称、描述、能力标签拼接为一段文本，
        以便生成语义向量用于搜索。
        """
        parts = [
            registration.agent_name,
            registration.description,
        ]
        if registration.capabilities:
            parts.append("Capabilities: " + ", ".join(registration.capabilities))
        return " | ".join(parts)
