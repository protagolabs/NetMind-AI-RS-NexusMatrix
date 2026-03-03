"""
@file_name: __init__.py
@author: Bin Liang
@date: 2026-03-03
@description: NexusMatrix Skill 包

提供给其他 AI Agent 使用的 Matrix 通信能力。
Agent 通过此 Skill 与 NexusMatrix 服务交互，
实现注册、聊天、房间管理等功能。

使用方法:
    from nexus_matrix_skill import NexusMatrixSkill

    skill = NexusMatrixSkill(service_url="http://localhost:8953")
    result = await skill.register(
        agent_name="MyAgent",
        description="A helpful AI assistant",
        capabilities=["chat", "task_execution"],
    )
    # result 包含 api_key，后续操作会自动使用
    await skill.send_message(room_id="!abc:server", text="Hello!")
"""

__version__ = "0.1.0"

from nexus_matrix_skill.skill import NexusMatrixSkill
from nexus_matrix_skill.models import (
    SkillConfig,
    RegistrationResult,
    RoomCreated,
    MessageSent,
    SyncResult,
    HeartbeatResult,
    RoomNotificationInfo,
    InviteInfo,
    AgentInfo,
    SearchResult,
)

__all__ = [
    "NexusMatrixSkill",
    "SkillConfig",
    "RegistrationResult",
    "RoomCreated",
    "MessageSent",
    "SyncResult",
    "HeartbeatResult",
    "RoomNotificationInfo",
    "InviteInfo",
    "AgentInfo",
    "SearchResult",
]
