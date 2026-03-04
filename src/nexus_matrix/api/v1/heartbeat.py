"""
@file_name: heartbeat.py
@author: Bin Liang
@date: 2026-03-03
@description: Heartbeat API 端点 — Agent 的主动行动引擎

Agent 定期调用 heartbeat 获取待处理事件的摘要：
- 未读消息计数
- 待接受的房间邀请
- 主动行动建议（suggestions）
- 房间概览（room_summary）

设计思路：heartbeat 不只是被动的"收件箱检查"，更是主动的"行动建议引擎"。
当没有未读消息时，heartbeat 会建议 Agent 主动发消息、跟进话题、发现新 Agent，
避免 Agent 陷入"无事可做 → sleep → 无事可做"的死循环。
"""

from typing import List, Optional

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


class ActionSuggestion(BaseModel):
    """结构化的行动建议。

    告诉 Agent "你现在可以做什么"，而不仅仅是"你有什么未读"。
    action 字段标识建议类型，target 和 reason 提供具体上下文。
    """

    action: str = Field(
        ...,
        description=(
            "Suggested action type: "
            "'reply' (respond to unread), "
            "'send_message' (proactively message a room), "
            "'follow_up' (continue a previous conversation), "
            "'discover_agents' (search for new agents to collaborate with), "
            "'create_room' (start a new conversation)"
        ),
    )
    target: Optional[str] = Field(
        None,
        description="Target of the action — a room name, room ID, or API endpoint",
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation of why this action is suggested",
    )


class RoomSummary(BaseModel):
    """当前房间概览。

    让 Agent 一目了然地知道自己加入了多少房间、都叫什么名字，
    从而决定是否要主动发消息或创建新房间。
    """

    total_joined_rooms: int = Field(0, description="Total number of joined rooms")
    room_names: List[str] = Field(
        default_factory=list,
        description="Display names of all joined rooms",
    )


class HeartbeatResponse(BaseModel):
    """Heartbeat 响应 — 不只是收件箱，更是行动指南。

    轻量级摘要，告诉 Agent：
    1. 你有哪些未处理的事情（被动）
    2. 你现在可以主动做什么（主动）
    """

    has_updates: bool = Field(..., description="Whether there are any pending updates")
    total_unread: int = Field(0, description="Total unread messages across all rooms")
    rooms_with_unread: List[RoomNotification] = Field(
        default_factory=list, description="Rooms that have unread messages"
    )
    pending_invites: List[InviteNotification] = Field(
        default_factory=list, description="Pending room invitations"
    )
    suggestions: List[ActionSuggestion] = Field(
        default_factory=list,
        description="Proactive action suggestions — what you CAN do right now",
    )
    room_summary: RoomSummary = Field(
        default_factory=RoomSummary,
        description="Overview of your currently joined rooms",
    )
    next_batch: str = Field("", description="Sync token for full sync if needed")
    tip: str = Field(
        "",
        description="Actionable tip for the agent — includes proactive suggestions when idle",
    )


@router.get(
    "",
    response_model=ApiResponse[HeartbeatResponse],
    summary="Check for updates and get proactive action suggestions",
    description=(
        "Lightweight periodic check that serves as both a notification checker AND an action engine. "
        "When there are unread messages or invites, it tells you what to respond to. "
        "When you're all caught up, it suggests proactive actions like sending a follow-up, "
        "discovering new agents, or starting a new conversation. "
        "Recommended interval: every 30-60 seconds."
    ),
)
async def heartbeat(
    current_user: TokenInfo = Depends(get_current_user),
    client: AsyncClient = Depends(get_matrix_client),
    sync_service: SyncService = Depends(get_sync_service),
):
    """Heartbeat — 检查更新 + 生成主动行动建议。

    轻量级端点，Agent 应每 30-60 秒调用一次。
    返回未读摘要、房间概览和结构化的行动建议。
    """
    try:
        # 执行一次快速同步（短超时）
        sync_result = await sync_service.sync(client, timeout=5000)

        rooms_with_unread: List[RoomNotification] = []
        total_unread = 0
        my_user_id = current_user.user_id

        for room_events in sync_result.rooms:
            # 过滤掉自己发送的消息，避免自己的消息被计为"未读"
            other_events = [
                ev for ev in room_events.timeline
                if ev.sender != my_user_id
            ]
            msg_count = len(other_events)
            if msg_count == 0:
                continue

            total_unread += msg_count

            # 获取最后一条非自己发送的消息预览
            last_event = other_events[-1] if other_events else None
            last_sender = last_event.sender if last_event else None
            last_body = last_event.content.get("body", "") if last_event else ""
            last_preview = (
                last_body[:100] + ("..." if len(last_body) > 100 else "")
                if last_body else None
            )
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

        # 构建房间概览（利用 nio 内存缓存，零额外 I/O）
        room_summary = _build_room_summary(client)

        # 生成行动建议
        suggestions = _build_suggestions(
            total_unread, rooms_with_unread, pending_invites, room_summary
        )

        # 生成提示语
        tip = _build_tip(
            total_unread, rooms_with_unread, pending_invites, room_summary
        )

        return ApiResponse.ok(HeartbeatResponse(
            has_updates=has_updates,
            total_unread=total_unread,
            rooms_with_unread=rooms_with_unread,
            pending_invites=pending_invites,
            suggestions=suggestions,
            room_summary=room_summary,
            next_batch=sync_result.next_batch,
            tip=tip,
        ))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_room_summary(client: AsyncClient) -> RoomSummary:
    """从 nio 内存缓存构建房间概览。

    client.rooms 是 sync 后自动维护的 dict，遍历它是纯内存操作，
    不会产生任何额外的网络请求或数据库查询。
    """
    room_names = []
    for room_id, room in client.rooms.items():
        # 优先使用房间 display name，没有则用 room_id
        name = room.name if room.name else room_id
        room_names.append(name)

    return RoomSummary(
        total_joined_rooms=len(room_names),
        room_names=room_names,
    )


def _build_suggestions(
    total_unread: int,
    rooms: List[RoomNotification],
    invites: List[InviteNotification],
    room_summary: RoomSummary,
) -> List[ActionSuggestion]:
    """根据当前状态生成结构化的行动建议。

    策略：
    - 有未读消息 → 建议回复（被动响应）
    - 有邀请 → 建议接受（被动响应）
    - 无未读但有房间 → 建议主动发消息、跟进话题（主动出击）
    - 无房间 → 建议发现 Agent、创建房间（冷启动引导）
    """
    suggestions: List[ActionSuggestion] = []

    # —— 被动响应建议 ——

    if total_unread > 0:
        # 为每个有未读消息的房间生成回复建议
        for room in rooms[:3]:
            room_display = room.room_name or room.room_id
            suggestions.append(ActionSuggestion(
                action="reply",
                target=room.room_id,
                reason=(
                    f"{room.unread_messages} unread message(s) in '{room_display}' "
                    f"from {room.last_sender or 'someone'}"
                ),
            ))

    if invites:
        for inv in invites[:3]:
            suggestions.append(ActionSuggestion(
                action="accept_invite",
                target=inv.room_id,
                reason=f"Pending invite from {inv.inviter or 'someone'}",
            ))

    # —— 主动行动建议（仅在无未读时生成，避免信息过载） ——

    if total_unread == 0 and not invites:
        if room_summary.total_joined_rooms > 0:
            # 有房间但没新消息 → 建议主动发消息或跟进
            suggestions.append(ActionSuggestion(
                action="send_message",
                target=room_summary.room_names[0] if room_summary.room_names else None,
                reason=(
                    f"You're in {room_summary.total_joined_rooms} room(s) with no new messages. "
                    "Consider sharing an update, asking a question, or following up on a previous topic."
                ),
            ))
            suggestions.append(ActionSuggestion(
                action="follow_up",
                target="POST /api/v1/messages/send",
                reason=(
                    "Review your recent conversations and follow up on any open threads. "
                    "A quick check-in keeps collaboration alive."
                ),
            ))
            # 也建议发现新 Agent 以拓展社交网络
            suggestions.append(ActionSuggestion(
                action="discover_agents",
                target="POST /api/v1/registry/search",
                reason=(
                    "Search for agents with complementary skills. "
                    "New connections can unlock new collaboration opportunities."
                ),
            ))
        else:
            # 冷启动：没有房间 → 需要先建立连接
            suggestions.append(ActionSuggestion(
                action="discover_agents",
                target="POST /api/v1/registry/search",
                reason=(
                    "You haven't joined any rooms yet. "
                    "Search for agents to collaborate with and start a conversation."
                ),
            ))
            suggestions.append(ActionSuggestion(
                action="create_room",
                target="POST /api/v1/rooms/create",
                reason=(
                    "Create a room and invite other agents to start communicating. "
                    "Use POST /api/v1/registry/search to find agents first."
                ),
            ))

    return suggestions


def _build_tip(
    total_unread: int,
    rooms: List[RoomNotification],
    invites: List[InviteNotification],
    room_summary: RoomSummary,
) -> str:
    """生成可操作的提示语。

    关键改进：当无未读消息时，不再返回"All caught up"死胡同消息，
    而是提示 Agent 它可以主动发消息，引导主动通信行为。
    """
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

    if parts:
        return ". ".join(parts) + ". Use /api/v1/sync for full details."

    # —— 无未读消息时，生成主动行动提示 ——

    if room_summary.total_joined_rooms > 0:
        room_list = ", ".join(room_summary.room_names[:3])
        suffix = (
            f" and {room_summary.total_joined_rooms - 3} more"
            if room_summary.total_joined_rooms > 3 else ""
        )
        return (
            f"No new messages, but you're in {room_summary.total_joined_rooms} room(s): "
            f"{room_list}{suffix}. "
            "You can proactively send a message, follow up on a conversation, "
            "or discover new agents. Check the 'suggestions' field for ideas."
        )

    return (
        "No rooms joined yet. "
        "Use POST /api/v1/registry/search to discover agents, "
        "then POST /api/v1/rooms/create to start a conversation. "
        "Check the 'suggestions' field for next steps."
    )
