"""
@file_name: sync_service.py
@author: Bin Liang
@date: 2026-03-03
@description: 同步服务

封装 Matrix 事件同步逻辑，支持：
- 增量同步（基于 next_batch token）
- 事件转换为内部数据模型
- 同步状态持久化
"""

from typing import Any, Dict, List, Optional

from nio import AsyncClient, SyncResponse as NioSyncResponse
from loguru import logger

from nexus_matrix.models.sync import RoomEvents, SyncResponse, TimelineEvent
from nexus_matrix.storage.database import Database


class SyncService:
    """同步服务。

    管理 Matrix /sync 调用，将原始同步响应转换为结构化的内部模型。
    支持增量同步，通过持久化 next_batch token 实现断点续传。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def sync(
        self,
        client: AsyncClient,
        timeout: int = 30000,
        since: Optional[str] = None,
    ) -> SyncResponse:
        """执行一次 Matrix 同步。

        Args:
            client: Matrix 客户端。
            timeout: 长轮询超时（毫秒）。
            since: 上次同步的 next_batch token，为空则全量同步。

        Returns:
            结构化的同步响应。
        """
        # 如果没有传入 since，尝试从数据库恢复
        if since is None:
            since = await self._get_sync_token(client.user_id)

        response = await client.sync(timeout=timeout, since=since or "")

        if isinstance(response, NioSyncResponse):
            # 持久化 next_batch
            await self._save_sync_token(client.user_id, response.next_batch)

            # 转换响应
            return self._convert_sync_response(response, client.user_id)
        else:
            raise RuntimeError(f"Sync failed: {response}")

    def _convert_sync_response(
        self, response: NioSyncResponse, user_id: str
    ) -> SyncResponse:
        """将 nio SyncResponse 转换为内部模型。"""
        rooms = []

        # 处理已加入的房间
        for room_id, room_info in response.rooms.join.items():
            timeline_events = []
            state_events = []

            # 转换 timeline 事件
            for event in room_info.timeline.events:
                # 跳过自己发送的消息
                if event.sender == user_id:
                    continue

                timeline_events.append(TimelineEvent(
                    event_id=event.event_id,
                    event_type=type(event).__name__,
                    room_id=room_id,
                    sender=event.sender,
                    timestamp=event.server_timestamp,
                    content=self._extract_content(event),
                ))

            # 转换 state 事件
            for event in room_info.state:
                state_events.append(TimelineEvent(
                    event_id=event.event_id,
                    event_type=type(event).__name__,
                    room_id=room_id,
                    sender=event.sender,
                    timestamp=event.server_timestamp,
                    content=self._extract_content(event),
                    state_key=getattr(event, "state_key", None),
                ))

            if timeline_events or state_events:
                # unread_notifications 可能是 dict 或 UnreadNotifications 对象
                unread = 0
                if hasattr(room_info, "unread_notifications"):
                    notif = room_info.unread_notifications
                    if isinstance(notif, dict):
                        unread = notif.get("notification_count", 0)
                    else:
                        unread = getattr(notif, "notification_count", 0) or 0

                rooms.append(RoomEvents(
                    room_id=room_id,
                    timeline=timeline_events,
                    state=state_events,
                    unread_count=unread,
                ))

        # 处理邀请
        invited_rooms = []
        for room_id, room_info in response.rooms.invite.items():
            invited_rooms.append({
                "room_id": room_id,
                "inviter": self._get_inviter(room_info),
            })

        return SyncResponse(
            next_batch=response.next_batch,
            rooms=rooms,
            invited_rooms=invited_rooms,
        )

    @staticmethod
    def _extract_content(event) -> Dict[str, Any]:
        """从 nio 事件对象中提取内容字典。"""
        content = {}
        if hasattr(event, "body"):
            content["body"] = event.body
            content["msgtype"] = getattr(event, "msgtype", "m.text")
        if hasattr(event, "formatted_body") and event.formatted_body:
            content["formatted_body"] = event.formatted_body
        if hasattr(event, "source") and isinstance(event.source, dict):
            content = event.source.get("content", content)
        return content

    @staticmethod
    def _get_inviter(room_info) -> Optional[str]:
        """从邀请信息中提取邀请者 ID。"""
        for event in room_info.invite_state:
            if hasattr(event, "sender"):
                return event.sender
        return None

    async def _get_sync_token(self, user_id: str) -> Optional[str]:
        """从数据库获取保存的 sync token。"""
        row = await self._db.fetch_one(
            "SELECT next_batch FROM sync_tokens WHERE user_id = ?",
            (user_id,),
        )
        return row["next_batch"] if row else None

    async def _save_sync_token(self, user_id: str, next_batch: str) -> None:
        """保存 sync token 到数据库。"""
        existing = await self._db.fetch_one(
            "SELECT user_id FROM sync_tokens WHERE user_id = ?",
            (user_id,),
        )
        if existing:
            await self._db.update(
                "sync_tokens",
                {"user_id": user_id},
                {"next_batch": next_batch},
            )
        else:
            await self._db.insert(
                "sync_tokens",
                {"user_id": user_id, "next_batch": next_batch},
            )
