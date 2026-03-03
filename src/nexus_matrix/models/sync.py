"""
@file_name: sync.py
@author: Bin Liang
@date: 2026-03-03
@description: 同步相关数据模型

定义 Matrix 事件同步、实时通知等功能所需的数据结构。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    """时间线事件（通用）。"""

    event_id: str = Field(..., description="Event ID")
    event_type: str = Field(..., description="Event type (e.g., m.room.message)")
    room_id: str = Field(..., description="Room ID")
    sender: str = Field(..., description="Sender user ID")
    timestamp: int = Field(..., description="Server timestamp (ms)")
    content: Dict[str, Any] = Field(default_factory=dict, description="Event content")
    state_key: Optional[str] = Field(None, description="State key (for state events)")


class RoomEvents(BaseModel):
    """单个房间的事件集合。"""

    room_id: str = Field(..., description="Room ID")
    timeline: List[TimelineEvent] = Field(
        default_factory=list, description="Timeline events"
    )
    state: List[TimelineEvent] = Field(
        default_factory=list, description="State events"
    )
    unread_count: int = Field(0, description="Unread message count")


class SyncResponse(BaseModel):
    """同步响应。

    包含自上次同步以来的所有新事件。
    客户端应保存 next_batch 用于下次增量同步。
    """

    next_batch: str = Field(..., description="Token for next incremental sync")
    rooms: List[RoomEvents] = Field(
        default_factory=list, description="Room events (joined rooms)"
    )
    invited_rooms: List[Dict[str, Any]] = Field(
        default_factory=list, description="Pending room invitations"
    )
    has_more: bool = Field(False, description="Whether more events are available")
