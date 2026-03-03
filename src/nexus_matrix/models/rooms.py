"""
@file_name: rooms.py
@author: Bin Liang
@date: 2026-03-03
@description: 房间管理相关数据模型

定义 Matrix 房间的创建、查询、成员管理等操作所需的数据结构。
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class RoomVisibility(str, Enum):
    """房间可见性。"""

    PUBLIC = "public"
    PRIVATE = "private"


class RoomPreset(str, Enum):
    """房间预设模板。"""

    PRIVATE_CHAT = "private_chat"
    PUBLIC_CHAT = "public_chat"
    TRUSTED_PRIVATE_CHAT = "trusted_private_chat"


class CreateRoomRequest(BaseModel):
    """创建房间请求。"""

    name: Optional[str] = Field(None, max_length=200, description="Room display name")
    topic: Optional[str] = Field(None, max_length=500, description="Room topic/description")
    room_alias: Optional[str] = Field(
        None, description="Local alias (e.g., 'general' becomes #general:server)"
    )
    visibility: RoomVisibility = Field(
        RoomVisibility.PRIVATE, description="Room visibility"
    )
    preset: RoomPreset = Field(
        RoomPreset.PRIVATE_CHAT, description="Room preset template"
    )
    invite: List[str] = Field(
        default_factory=list, description="List of user IDs to invite"
    )
    is_direct: bool = Field(
        False, description="Whether this is a direct message room"
    )
    initial_state: Optional[List[Dict]] = Field(
        None, description="Initial state events for the room"
    )


class CreateRoomResponse(BaseModel):
    """创建房间响应。"""

    room_id: str = Field(..., description="Matrix room ID (e.g., !abc:server)")
    room_alias: Optional[str] = Field(None, description="Room alias if set")


class RoomMember(BaseModel):
    """房间成员信息。"""

    user_id: str = Field(..., description="Member's Matrix user ID")
    display_name: Optional[str] = Field(None, description="Display name")
    membership: str = Field(..., description="Membership state (join/invite/leave/ban)")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")


class RoomInfo(BaseModel):
    """房间详细信息。"""

    room_id: str = Field(..., description="Matrix room ID")
    name: Optional[str] = Field(None, description="Room name")
    topic: Optional[str] = Field(None, description="Room topic")
    canonical_alias: Optional[str] = Field(None, description="Primary room alias")
    member_count: int = Field(0, description="Number of joined members")
    is_direct: bool = Field(False, description="Whether this is a DM room")
    is_encrypted: bool = Field(False, description="Whether E2EE is enabled")


class JoinRoomRequest(BaseModel):
    """加入房间请求。

    兼容多种字段名：room_id_or_alias / room_id / room_alias / room，
    Agent 可以用任意一种发送请求。
    """

    room_id_or_alias: Optional[str] = Field(
        None, description="Room ID or alias to join"
    )
    room_id: Optional[str] = Field(None, description="Room ID (alias for room_id_or_alias)")
    room_alias: Optional[str] = Field(None, description="Room alias (alias for room_id_or_alias)")
    room: Optional[str] = Field(None, description="Alias for room_id_or_alias")
    target: Optional[str] = Field(None, description="Alias for room_id_or_alias")

    @model_validator(mode="after")
    def _resolve_room_target(self) -> "JoinRoomRequest":
        """将所有可能的字段名统一合并到 room_id_or_alias。"""
        target = (
            self.room_id_or_alias or self.room_id or self.room_alias
            or self.room or self.target
        )
        if not target:
            raise ValueError(
                "At least one of room_id_or_alias, room_id, room_alias, "
                "room, or target must be provided"
            )
        self.room_id_or_alias = target
        return self


class InviteRequest(BaseModel):
    """邀请用户请求。"""

    user_id: str = Field(..., description="User ID to invite")
