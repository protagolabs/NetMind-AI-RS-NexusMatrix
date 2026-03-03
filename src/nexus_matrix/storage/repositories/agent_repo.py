"""
@file_name: agent_repo.py
@author: Bin Liang
@date: 2026-03-03
@description: Agent 数据仓库

封装对 agents 表的所有 CRUD 操作，
将数据库行转换为 AgentProfile 领域模型。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from nexus_matrix.models.registry import AgentProfile, AgentStatus
from nexus_matrix.storage.database import Database


class AgentRepository:
    """Agent 数据仓库。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _row_to_profile(self, row: Dict[str, Any]) -> AgentProfile:
        """将数据库行转换为 AgentProfile。"""
        capabilities = row.get("capabilities", "[]")
        if isinstance(capabilities, str):
            capabilities = json.loads(capabilities)

        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AgentProfile(
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            matrix_user_id=row["matrix_user_id"],
            description=row["description"],
            capabilities=capabilities,
            metadata=metadata if metadata else None,
            webhook_url=row.get("webhook_url"),
            owner=row.get("owner"),
            status=AgentStatus(row.get("status", "active")),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def create(
        self,
        agent_id: str,
        agent_name: str,
        matrix_user_id: str,
        description: str,
        capabilities: List[str],
        metadata: Optional[Dict[str, str]] = None,
        webhook_url: Optional[str] = None,
        owner: Optional[str] = None,
        embedding: Optional[bytes] = None,
    ) -> AgentProfile:
        """创建新 Agent 记录。"""
        now = datetime.utcnow().isoformat()
        data = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "matrix_user_id": matrix_user_id,
            "description": description,
            "capabilities": json.dumps(capabilities),
            "metadata": json.dumps(metadata or {}),
            "webhook_url": webhook_url,
            "owner": owner,
            "status": AgentStatus.ACTIVE.value,
            "embedding": embedding,
            "created_at": now,
            "updated_at": now,
        }
        await self._db.insert("agents", data)
        return await self.get_by_id(agent_id)

    async def get_by_id(self, agent_id: str) -> Optional[AgentProfile]:
        """根据 agent_id 查询。"""
        row = await self._db.fetch_one(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        )
        return self._row_to_profile(row) if row else None

    async def get_by_matrix_user_id(self, matrix_user_id: str) -> Optional[AgentProfile]:
        """根据 Matrix User ID 查询。"""
        row = await self._db.fetch_one(
            "SELECT * FROM agents WHERE matrix_user_id = ?", (matrix_user_id,)
        )
        return self._row_to_profile(row) if row else None

    async def list_active(self, limit: int = 100, offset: int = 0) -> List[AgentProfile]:
        """列出所有活跃 Agent。"""
        rows = await self._db.fetch_all(
            "SELECT * FROM agents WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (AgentStatus.ACTIVE.value, limit, offset),
        )
        return [self._row_to_profile(r) for r in rows]

    async def count_active(self) -> int:
        """统计活跃 Agent 数量。"""
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as cnt FROM agents WHERE status = ?",
            (AgentStatus.ACTIVE.value,),
        )
        return row["cnt"] if row else 0

    async def update(self, agent_id: str, data: Dict[str, Any]) -> Optional[AgentProfile]:
        """更新 Agent 信息。"""
        data["updated_at"] = datetime.utcnow().isoformat()
        # 序列化列表/字典字段
        for key in ("capabilities", "metadata"):
            if key in data and isinstance(data[key], (list, dict)):
                data[key] = json.dumps(data[key])
        await self._db.update("agents", {"agent_id": agent_id}, data)
        return await self.get_by_id(agent_id)

    async def delete(self, agent_id: str) -> bool:
        """删除 Agent（级联删除 API Keys）。"""
        count = await self._db.delete("agents", {"agent_id": agent_id})
        return count > 0

    async def get_all_with_embeddings(self) -> List[tuple]:
        """获取所有有 embedding 的 Agent（用于语义搜索）。

        Returns:
            列表，每项为 (AgentProfile, np.ndarray)。
        """
        rows = await self._db.fetch_all(
            "SELECT * FROM agents WHERE status = ? AND embedding IS NOT NULL",
            (AgentStatus.ACTIVE.value,),
        )
        results = []
        for row in rows:
            profile = self._row_to_profile(row)
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)
            results.append((profile, embedding))
        return results

    async def update_embedding(self, agent_id: str, embedding: bytes) -> None:
        """更新 Agent 的 embedding 向量。"""
        await self._db.update(
            "agents",
            {"agent_id": agent_id},
            {"embedding": embedding, "updated_at": datetime.utcnow().isoformat()},
        )
