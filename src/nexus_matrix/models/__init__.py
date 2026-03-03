"""
@file_name: __init__.py
@author: Bin Liang
@date: 2026-03-03
@description: Pydantic 数据模型集合

统一导出所有模型，方便外部引用。
"""

from nexus_matrix.models.common import ApiResponse, PaginatedResponse, ErrorDetail
from nexus_matrix.models.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    TokenInfo,
)
from nexus_matrix.models.rooms import (
    CreateRoomRequest,
    CreateRoomResponse,
    RoomInfo,
    RoomMember,
    JoinRoomRequest,
    InviteRequest,
)
from nexus_matrix.models.messages import (
    SendMessageRequest,
    SendMessageResponse,
    MessageEvent,
    MessageHistory,
)
from nexus_matrix.models.registry import (
    AgentRegistration,
    AgentProfile,
    AgentSearchRequest,
    AgentSearchResult,
)
from nexus_matrix.models.sync import SyncResponse, RoomEvents, TimelineEvent

__all__ = [
    "ApiResponse", "PaginatedResponse", "ErrorDetail",
    "LoginRequest", "LoginResponse", "RegisterRequest", "RegisterResponse", "TokenInfo",
    "CreateRoomRequest", "CreateRoomResponse", "RoomInfo", "RoomMember",
    "JoinRoomRequest", "InviteRequest",
    "SendMessageRequest", "SendMessageResponse", "MessageEvent", "MessageHistory",
    "AgentRegistration", "AgentProfile", "AgentSearchRequest", "AgentSearchResult",
    "SyncResponse", "RoomEvents", "TimelineEvent",
]
