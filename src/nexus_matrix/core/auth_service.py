"""
@file_name: auth_service.py
@author: Bin Liang
@date: 2026-03-03
@description: 认证服务

处理 Matrix 用户注册、登录、API Key 管理等认证逻辑。
通过 Synapse Admin API 程序化创建用户，避免开放公共注册。
"""

import hashlib
import hmac
from typing import Optional

import httpx
from loguru import logger

from nexus_matrix.config import Settings
from nexus_matrix.core.matrix_client_manager import MatrixClientManager
from nexus_matrix.models.auth import (
    LoginResponse,
    RegisterResponse,
    TokenInfo,
)
from nexus_matrix.storage.repositories.agent_repo import AgentRepository
from nexus_matrix.storage.repositories.api_key_repo import ApiKeyRepository
from nexus_matrix.utils.security import generate_api_key, generate_id, hash_api_key


class AuthService:
    """认证服务。

    核心职责：
    - 通过 Synapse Admin API 注册 Matrix 用户
    - 管理 API Key 的生成和校验
    - 登录与 Token 管理
    """

    def __init__(
        self,
        settings: Settings,
        client_manager: MatrixClientManager,
        agent_repo: AgentRepository,
        api_key_repo: ApiKeyRepository,
    ) -> None:
        self._settings = settings
        self._client_manager = client_manager
        self._agent_repo = agent_repo
        self._api_key_repo = api_key_repo

    async def register_matrix_user(
        self, username: str, password: str, display_name: Optional[str] = None, admin: bool = False
    ) -> dict:
        """通过 Synapse Admin API 注册新的 Matrix 用户。

        使用 registration_shared_secret 生成 HMAC 签名，
        绕过公共注册限制，安全地创建用户。

        Args:
            username: 用户名（localpart）。
            password: 密码。
            display_name: 显示名称。
            admin: 是否为管理员。

        Returns:
            包含 user_id, access_token, device_id 的字典。
        """
        shared_secret = self._settings.matrix_registration_secret
        homeserver = self._settings.matrix_homeserver_url

        if not shared_secret:
            # 无 shared_secret 时，尝试直接通过 client API 注册
            return await self._register_via_client_api(username, password, display_name)

        async with httpx.AsyncClient() as http:
            # Step 1: 获取 nonce
            nonce_resp = await http.get(f"{homeserver}/_synapse/admin/v1/register")
            nonce_resp.raise_for_status()
            nonce = nonce_resp.json()["nonce"]

            # Step 2: 构造 HMAC 签名
            mac = hmac.new(
                shared_secret.encode("utf-8"),
                digestmod=hashlib.sha1,
            )
            mac.update(nonce.encode("utf-8"))
            mac.update(b"\x00")
            mac.update(username.encode("utf-8"))
            mac.update(b"\x00")
            mac.update(password.encode("utf-8"))
            mac.update(b"\x00")
            mac.update(b"admin" if admin else b"notadmin")
            hex_mac = mac.hexdigest()

            # Step 3: 注册用户
            register_data = {
                "nonce": nonce,
                "username": username,
                "password": password,
                "mac": hex_mac,
                "admin": admin,
            }
            if display_name:
                register_data["displayname"] = display_name

            reg_resp = await http.post(
                f"{homeserver}/_synapse/admin/v1/register",
                json=register_data,
            )

            # 处理用户已存在的情况：用 Admin API 重置密码再登录
            if reg_resp.status_code == 400:
                error_body = reg_resp.json()
                if "User ID already taken" in str(error_body):
                    logger.info(f"Matrix 用户 @{username}:{self._settings.matrix_server_name} 已存在，通过 Admin API 重置密码")
                    user_id = f"@{username}:{self._settings.matrix_server_name}"

                    # 用 Admin API 重置密码
                    admin_client = self._client_manager.admin_client
                    if admin_client and admin_client.access_token:
                        reset_resp = await http.put(
                            f"{homeserver}/_synapse/admin/v2/users/{user_id}",
                            headers={"Authorization": f"Bearer {admin_client.access_token}"},
                            json={"password": password},
                        )
                        if reset_resp.status_code == 200:
                            logger.info(f"密码已重置，正在登录 {user_id}")
                        else:
                            logger.warning(f"Admin API 重置密码失败: {reset_resp.status_code}")

                    # 用新密码登录
                    login_resp = await http.post(
                        f"{homeserver}/_matrix/client/v3/login",
                        json={
                            "type": "m.login.password",
                            "identifier": {"type": "m.id.user", "user": username},
                            "password": password,
                        },
                    )
                    login_resp.raise_for_status()
                    login_result = login_resp.json()
                    return {
                        "user_id": login_result["user_id"],
                        "access_token": login_result["access_token"],
                        "device_id": login_result.get("device_id", ""),
                    }

            reg_resp.raise_for_status()
            result = reg_resp.json()

            logger.info(f"Matrix 用户已注册: {result.get('user_id')}")
            return {
                "user_id": result["user_id"],
                "access_token": result["access_token"],
                "device_id": result.get("device_id", ""),
            }

    async def _register_via_client_api(
        self, username: str, password: str, display_name: Optional[str] = None
    ) -> dict:
        """通过 Matrix Client API 注册（备选方案）。

        当 Synapse Admin API 不可用时使用此方法。

        Args:
            username: 用户名。
            password: 密码。
            display_name: 显示名称。

        Returns:
            包含 user_id, access_token, device_id 的字典。
        """
        homeserver = self._settings.matrix_homeserver_url
        async with httpx.AsyncClient() as http:
            payload = {
                "auth": {"type": "m.login.dummy"},
                "username": username,
                "password": password,
            }
            if display_name:
                payload["initial_device_display_name"] = display_name

            resp = await http.post(
                f"{homeserver}/_matrix/client/v3/register",
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()

            return {
                "user_id": result["user_id"],
                "access_token": result["access_token"],
                "device_id": result.get("device_id", ""),
            }

    async def register_agent(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> RegisterResponse:
        """注册 Agent：创建 Matrix 用户 + 生成 API Key。

        完整注册流程：
        1. 在 Matrix homeserver 创建用户
        2. 确保 agents 表有对应记录（满足 FK 约束）
        3. 生成 NexusMatrix API Key
        4. 将 API Key 哈希存入数据库

        Args:
            username: 用户名。
            password: 密码。
            display_name: 显示名称。
            agent_id: 外部传入的 Agent ID（由 RegistryService 统一分配）。

        Returns:
            注册结果。
        """
        # 在 Matrix 创建用户
        matrix_result = await self.register_matrix_user(
            username, password, display_name
        )

        user_id = matrix_result["user_id"]
        access_token = matrix_result["access_token"]
        device_id = matrix_result["device_id"]

        # 确保 agents 表有记录（满足 api_keys 的 FK 约束）
        existing_agent = await self._agent_repo.get_by_matrix_user_id(user_id)
        if existing_agent:
            agent_id = existing_agent.agent_id
        else:
            if not agent_id:
                agent_id = generate_id("agt")
            await self._agent_repo.create(
                agent_id=agent_id,
                agent_name=display_name or username,
                matrix_user_id=user_id,
                description="",
                capabilities=[],
            )

        # 生成 API Key
        api_key = generate_api_key()
        key_id = generate_id("key")

        # 存储 API Key 哈希
        await self._api_key_repo.create(
            key_id=key_id,
            api_key_hash=hash_api_key(api_key),
            agent_id=agent_id,
            matrix_user_id=user_id,
            access_token=access_token,
            device_id=device_id,
        )

        # 在客户端池中创建连接
        await self._client_manager.create_client(user_id, access_token, device_id)

        return RegisterResponse(
            user_id=user_id,
            api_key=api_key,
            access_token=access_token,
            device_id=device_id,
        )

    async def login(self, username: str, password: str) -> LoginResponse:
        """登录：验证凭据并返回 token + API Key。

        Args:
            username: 用户名或 MXID。
            password: 密码。

        Returns:
            登录结果。
        """
        user_id, access_token, device_id = await self._client_manager.login_with_password(
            username, password
        )

        # 查找或创建 API Key
        agent = await self._agent_repo.get_by_matrix_user_id(user_id)
        if agent:
            key_record = await self._api_key_repo.get_by_agent_id(agent.agent_id)
            if key_record:
                # 更新 access_token
                await self._api_key_repo.update_access_token(
                    agent.agent_id, access_token, device_id
                )
                # 生成新 API Key
                api_key = generate_api_key()
                key_id = generate_id("key")
                await self._api_key_repo.create(
                    key_id=key_id,
                    api_key_hash=hash_api_key(api_key),
                    agent_id=agent.agent_id,
                    matrix_user_id=user_id,
                    access_token=access_token,
                    device_id=device_id,
                )
                return LoginResponse(
                    user_id=user_id,
                    access_token=access_token,
                    device_id=device_id,
                    api_key=api_key,
                )

        # 未注册的用户：先创建 agent 记录再生成 API Key
        api_key = generate_api_key()
        key_id = generate_id("key")
        agent_id = generate_id("agt")

        # 创建最小化 agent 记录以满足 FK 约束
        await self._agent_repo.create(
            agent_id=agent_id,
            agent_name=username,
            matrix_user_id=user_id,
            description="",
            capabilities=[],
        )

        await self._api_key_repo.create(
            key_id=key_id,
            api_key_hash=hash_api_key(api_key),
            agent_id=agent_id,
            matrix_user_id=user_id,
            access_token=access_token,
            device_id=device_id,
        )

        return LoginResponse(
            user_id=user_id,
            access_token=access_token,
            device_id=device_id,
            api_key=api_key,
        )

    async def validate_api_key(self, api_key: str) -> Optional[TokenInfo]:
        """校验 API Key 并返回关联信息。

        Args:
            api_key: API Key 明文。

        Returns:
            Token 信息，无效时返回 None。
        """
        key_hash = hash_api_key(api_key)
        record = await self._api_key_repo.get_by_hash(key_hash)
        if not record:
            return None

        return TokenInfo(
            user_id=record["matrix_user_id"],
            agent_id=record["agent_id"],
            is_admin=bool(record.get("is_admin", 0)),
        )

    async def get_access_token(self, api_key: str) -> Optional[str]:
        """根据 API Key 获取对应的 Matrix access token。

        Args:
            api_key: API Key 明文。

        Returns:
            Matrix access token，无效时返回 None。
        """
        key_hash = hash_api_key(api_key)
        record = await self._api_key_repo.get_by_hash(key_hash)
        return record["access_token"] if record else None
