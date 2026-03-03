"""
@file_name: heartbeat.py
@author: Bin Liang
@date: 2026-03-03
@description: Heartbeat API 端点

Agent 定期调用 heartbeat 获取待处理事件的摘要：
- 未读消息计数
- 待接受的房间邀请
- 其他需要关注的状态变更

设计思路：heartbeat 是轻量级的"收件箱检查"，不返回完整消息内容。
Agent 看到有未读内容后，再调用 /sync 或 /messages 获取详情。
类比微信：heartbeat = 看到红点通知，sync = 打开聊天看具体消息。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from nio import AsyncClient
from pydantic import BaseModel, Field

from nexus_matrix.api.deps import get_current_user, get_matrix_client, get_sync_service
from nexus_matrix.core.sync_service import SyncService
from nexus_matrix.models.auth import TokenInfo
from nexus_matrix.models.common import ApiResponse

router = APIRouter(prefix="/heartbeat", tags=["Heartbeat"])


class RoomNotification(BaseModel):
    """单个房间的通知摘要。"""

    room_id: str = Field(..., description="Room ID")
    room_name: Optional[str] = Field(None, description="Room display name")
    unread_messages: int = Field(0, description="Number of unread messages")
    last_sender: Optional[str] = Field(None, description="Last message sender")
    last_message_preview: Optional[str] = Field(
        None, description="Preview of the last message (truncated to 100 chars)"
    )
    last_timestamp: Optional[int] = Field(None, description="Timestamp of the last event (ms)")


class InviteNotification(BaseModel):
    """房间邀请通知。"""

    room_id: str = Field(..., description="Room ID")
    inviter: Optional[str] = Field(None, description="Who invited you")


class HeartbeatResponse(BaseModel):
    """Heartbeat 响应。

    轻量级摘要，告诉 Agent "你有哪些未处理的事情"。
    """

    has_updates: bool = Field(..., description="Whether there are any pending updates")
    total_unread: int = Field(0, description="Total unread messages across all rooms")
    rooms_with_unread: List[RoomNotification] = Field(
        default_factory=list, description="Rooms that have unread messages"
    )
    pending_invites: List[InviteNotification] = Field(
        default_factory=list, description="Pending room invitations"
    )
    next_batch: str = Field("", description="Sync token for full sync if needed")
    tip: str = Field(
        "",
        description="Actionable tip for the agent (e.g., 'You have 3 unread messages in #general')",
    )


@router.get(
    "",
    response_model=ApiResponse[HeartbeatResponse],
    summary="Check for new messages, invites, and updates",
    description=(
        "Lightweight periodic check — like glancing at your phone's notification badges. "
        "Returns a summary of unread messages and pending invites without full message content. "
        "Call /api/v1/sync for full event details when has_updates is true. "
        "Recommended interval: every 30-60 seconds."
    ),
)
async def heartbeat(
    current_user: TokenInfo = Depends(get_current_user),
    client: AsyncClient = Depends(get_matrix_client),
    sync_service: SyncService = Depends(get_sync_service),
):
    """Heartbeat — 检查是否有新消息/邀请。

    轻量级端点，Agent 应每 30-60 秒调用一次。
    只返回摘要信息，不返回完整消息内容。
    """
    try:
        # 执行一次快速同步（短超时）
        sync_result = await sync_service.sync(client, timeout=5000)

        rooms_with_unread: List[RoomNotification] = []
        total_unread = 0

        for room_events in sync_result.rooms:
            msg_count = len(room_events.timeline)
            if msg_count == 0:
                continue

            total_unread += msg_count

            # 获取最后一条消息的预览
            last_event = room_events.timeline[-1] if room_events.timeline else None
            last_sender = last_event.sender if last_event else None
            last_body = last_event.content.get("body", "") if last_event else ""
            last_preview = last_body[:100] + ("..." if len(last_body) > 100 else "") if last_body else None
            last_ts = last_event.timestamp if last_event else None

            # 尝试获取房间名称
            room = client.rooms.get(room_events.room_id)
            room_name = room.name if room else None

            rooms_with_unread.append(RoomNotification(
                room_id=room_events.room_id,
                room_name=room_name,
                unread_messages=msg_count,
                last_sender=last_sender,
                last_message_preview=last_preview,
                last_timestamp=last_ts,
            ))

        # 处理邀请
        pending_invites = [
            InviteNotification(
                room_id=inv.get("room_id", ""),
                inviter=inv.get("inviter"),
            )
            for inv in sync_result.invited_rooms
        ]

        has_updates = total_unread > 0 or len(pending_invites) > 0

        # 生成提示语
        tip = _build_tip(total_unread, rooms_with_unread, pending_invites)

        return ApiResponse.ok(HeartbeatResponse(
            has_updates=has_updates,
            total_unread=total_unread,
            rooms_with_unread=rooms_with_unread,
            pending_invites=pending_invites,
            next_batch=sync_result.next_batch,
            tip=tip,
        ))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_tip(
    total_unread: int,
    rooms: List[RoomNotification],
    invites: List[InviteNotification],
) -> str:
    """生成可操作的提示语。"""
    parts = []

    if total_unread > 0:
        room_names = [r.room_name or r.room_id for r in rooms[:3]]
        parts.append(
            f"You have {total_unread} unread message(s) in: {', '.join(room_names)}"
        )

    if invites:
        inviters = [inv.inviter or "someone" for inv in invites[:3]]
        parts.append(
            f"You have {len(invites)} pending room invite(s) from: {', '.join(inviters)}"
        )

    if not parts:
        return "All caught up — no new messages or invites."

    return ". ".join(parts) + ". Use /api/v1/sync for full details."
