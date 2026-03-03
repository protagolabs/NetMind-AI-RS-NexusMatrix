"""
@file_name: api_key_repo.py
@author: Bin Liang
@date: 2026-03-03
@description: API Key 数据仓库

封装对 api_keys 表的所有 CRUD 操作，
管理 Agent 的 API 访问凭据。
"""

from datetime import datetime
from typing import Any, Dict, Optional

from nexus_matrix.storage.database import Database


class ApiKeyRepository:
    """API Key 数据仓库。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        key_id: str,
        api_key_hash: str,
        agent_id: str,
        matrix_user_id: str,
        access_token: str,
        device_id: str = "",
        is_admin: bool = False,
        expires_at: Optional[str] = None,
    ) -> None:
        """创建新的 API Key 记录。"""
        await self._db.insert("api_keys", {
            "key_id": key_id,
            "api_key_hash": api_key_hash,
            "agent_id": agent_id,
            "matrix_user_id": matrix_user_id,
            "access_token": access_token,
            "device_id": device_id,
            "is_admin": 1 if is_admin else 0,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at,
        })

    async def get_by_hash(self, api_key_hash: str) -> Optional[Dict[str, Any]]:
        """根据 API Key 哈希查询。"""
        return await self._db.fetch_one(
            "SELECT * FROM api_keys WHERE api_key_hash = ?",
            (api_key_hash,),
        )

    async def get_by_agent_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """根据 agent_id 查询其 API Key 记录。"""
        return await self._db.fetch_one(
            "SELECT * FROM api_keys WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )

    async def delete_by_agent_id(self, agent_id: str) -> int:
        """删除某 Agent 的所有 API Key。"""
        return await self._db.delete("api_keys", {"agent_id": agent_id})

    async def update_access_token(
        self, agent_id: str, access_token: str, device_id: str
    ) -> None:
        """更新 Agent 的 Matrix access token。"""
        await self._db.update(
            "api_keys",
            {"agent_id": agent_id},
            {"access_token": access_token, "device_id": device_id},
        )
