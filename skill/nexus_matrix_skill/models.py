"""
@file_name: models.py
@author: Bin Liang
@date: 2026-03-03
@description: Skill 数据模型

定义 Skill 包内部使用的数据结构，
尽量轻量，不依赖 pydantic（减少依赖体积）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillConfig:
    """Skill 配置。"""

    service_url: str = "http://localhost:8953"
    api_key: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3


@dataclass
class RegistrationResult:
    """注册结果。"""

    agent_id: str
    agent_name: str
    matrix_user_id: str
    api_key: str


@dataclass
class RoomCreated:
    """房间创建结果。"""

    room_id: str
    room_alias: Optional[str] = None


@dataclass
class MessageSent:
    """消息发送结果。"""

    event_id: str
    room_id: str


@dataclass
class MessageReceived:
    """收到的消息。"""

    event_id: str
    room_id: str
    sender: str
    body: str
    timestamp: int
    msg_type: str = "m.text"


@dataclass
class SyncResult:
    """同步结果。"""

    next_batch: str
    messages: List[MessageReceived] = field(default_factory=list)
    invited_rooms: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentInfo:
    """Agent 信息。"""

    agent_id: str
    agent_name: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    matrix_user_id: str = ""
    status: str = "active"


@dataclass
class RoomNotificationInfo:
    """房间未读通知摘要。"""

    room_id: str
    room_name: Optional[str] = None
    unread_messages: int = 0
    last_sender: Optional[str] = None
    last_message_preview: Optional[str] = None
    last_timestamp: Optional[int] = None


@dataclass
class InviteInfo:
    """待处理的房间邀请。"""

    room_id: str
    inviter: Optional[str] = None


@dataclass
class HeartbeatResult:
    """Heartbeat 检查结果。"""

    has_updates: bool
    total_unread: int = 0
    rooms_with_unread: List[RoomNotificationInfo] = field(default_factory=list)
    pending_invites: List[InviteInfo] = field(default_factory=list)
    next_batch: str = ""
    tip: str = ""


@dataclass
class SearchResult:
    """搜索结果。"""

    agent: AgentInfo
    score: float
