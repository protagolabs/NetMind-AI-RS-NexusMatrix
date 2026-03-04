"""
@file_name: feedback_repo.py
@author: Bin Liang
@date: 2026-03-03
@description: 反馈数据仓库

封装对 feedback 表的所有 CRUD 操作，
将数据库行转换为 FeedbackRecord 领域模型。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from nexus_matrix.models.feedback import (
    FeedbackCategory,
    FeedbackRecord,
    FeedbackStatus,
)
from nexus_matrix.storage.database import Database


class FeedbackRepository:
    """反馈数据仓库。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _row_to_record(self, row: Dict[str, Any]) -> FeedbackRecord:
        """将数据库行转换为 FeedbackRecord。"""
        # 反序列化 context JSON 字段
        context = row.get("context", "{}")
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except (json.JSONDecodeError, TypeError):
                context = {}

        return FeedbackRecord(
            feedback_id=row["feedback_id"],
            agent_id=row["agent_id"],
            agent_name=row.get("agent_name", ""),
            category=FeedbackCategory(row.get("category", "bug_report")),
            title=row["title"],
            content=row["content"],
            context=context if context else None,
            status=FeedbackStatus(row.get("status", "pending")),
            resolution=row.get("resolution"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def create(
        self,
        feedback_id: str,
        agent_id: str,
        agent_name: str,
        category: FeedbackCategory,
        title: str,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> FeedbackRecord:
        """创建反馈记录。

        Args:
            feedback_id: 反馈 ID（fb_xxxxxxxx）。
            agent_id: 提交者 Agent ID。
            agent_name: 提交者 Agent 名称。
            category: 反馈类别。
            title: 反馈标题。
            content: 反馈详细内容。
            context: 可选的附加上下文信息。

        Returns:
            创建后的 FeedbackRecord。
        """
        now = datetime.utcnow().isoformat()
        data = {
            "feedback_id": feedback_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "category": category.value,
            "title": title,
            "content": content,
            "context": json.dumps(context or {}),
            "status": FeedbackStatus.PENDING.value,
            "resolution": None,
            "created_at": now,
            "updated_at": now,
        }
        await self._db.insert("feedback", data)
        return await self.get_by_id(feedback_id)

    async def get_by_id(self, feedback_id: str) -> Optional[FeedbackRecord]:
        """根据 feedback_id 查询单条反馈。"""
        row = await self._db.fetch_one(
            "SELECT * FROM feedback WHERE feedback_id = ?", (feedback_id,)
        )
        return self._row_to_record(row) if row else None

    async def list_by_status(
        self,
        status: FeedbackStatus,
        limit: int = 20,
        offset: int = 0,
    ) -> List[FeedbackRecord]:
        """按状态列出反馈。"""
        rows = await self._db.fetch_all(
            "SELECT * FROM feedback WHERE status = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status.value, limit, offset),
        )
        return [self._row_to_record(r) for r in rows]

    async def list_by_agent(
        self,
        agent_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[FeedbackRecord]:
        """列出指定 Agent 提交的反馈。"""
        rows = await self._db.fetch_all(
            "SELECT * FROM feedback WHERE agent_id = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (agent_id, limit, offset),
        )
        return [self._row_to_record(r) for r in rows]

    async def list_unresolved(self, limit: int = 50) -> List[FeedbackRecord]:
        """列出所有未解决的反馈（pending + in_progress）。

        供巡检脚本使用，按创建时间升序排列（先处理最早的）。
        """
        rows = await self._db.fetch_all(
            "SELECT * FROM feedback WHERE status IN (?, ?) "
            "ORDER BY created_at ASC LIMIT ?",
            (FeedbackStatus.PENDING.value, FeedbackStatus.IN_PROGRESS.value, limit),
        )
        return [self._row_to_record(r) for r in rows]

    async def update_status(
        self,
        feedback_id: str,
        status: FeedbackStatus,
        resolution: Optional[str] = None,
    ) -> Optional[FeedbackRecord]:
        """更新反馈状态。

        Args:
            feedback_id: 反馈 ID。
            status: 新状态。
            resolution: 解决说明（当状态为 resolved/wont_fix 时提供）。

        Returns:
            更新后的 FeedbackRecord，若不存在则返回 None。
        """
        data: Dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if resolution is not None:
            data["resolution"] = resolution

        count = await self._db.update(
            "feedback", {"feedback_id": feedback_id}, data
        )
        if count == 0:
            return None
        return await self.get_by_id(feedback_id)

    async def count_by_status(self) -> Dict[str, int]:
        """按状态统计反馈数量。

        Returns:
            状态到数量的映射，如 {"pending": 3, "resolved": 10, ...}。
        """
        rows = await self._db.fetch_all(
            "SELECT status, COUNT(*) as cnt FROM feedback GROUP BY status"
        )
        return {row["status"]: row["cnt"] for row in rows}

    async def count_by_agent(self, agent_id: str) -> int:
        """统计指定 Agent 的反馈总数。"""
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as cnt FROM feedback WHERE agent_id = ?",
            (agent_id,),
        )
        return row["cnt"] if row else 0
