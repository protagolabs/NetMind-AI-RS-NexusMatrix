"""
@file_name: skill.py
@author: Bin Liang
@date: 2026-03-03
@description: NexusMatrix Skill 主接口

面向 AI Agent 的高层 API，封装所有 Matrix 通信功能。
设计原则：
- 零外部依赖（仅使用 Python 标准库）
- 同步接口（兼容所有 Agent 框架）
- 自动管理认证状态
- 清晰的错误信息
"""

import logging
from typing import Dict, List, Optional

from nexus_matrix_skill.client import NexusMatrixClient
from nexus_matrix_skill.models import (
    AgentInfo,
    HeartbeatResult,
    InviteInfo,
    MessageReceived,
    MessageSent,
    RegistrationResult,
    RoomCreated,
    RoomNotificationInfo,
    SearchResult,
    SkillConfig,
    SyncResult,
)

logger = logging.getLogger("nexus_matrix_skill")


class NexusMatrixSkill:
    """NexusMatrix Skill - AI Agent 的 Matrix 通信能力。

    提供完整的 Matrix 通信功能：
    - 注册/登录
    - 创建/加入/管理房间
    - 发送/接收消息
    - 同步事件
    - 搜索/发现其他 Agent

    使用方法:
        skill = NexusMatrixSkill("http://localhost:8953")

        # 注册
        result = skill.register(
            agent_name="MyAgent",
            description="A helpful assistant",
            capabilities=["chat"],
        )

        # 创建房间并发消息
        room = skill.create_room(name="test-room")
        skill.send_message(room.room_id, "Hello, Matrix!")

        # 同步接收消息
        sync = skill.sync()
        for msg in sync.messages:
            print(f"{msg.sender}: {msg.body}")
    """

    def __init__(
        self,
        service_url: str = "http://localhost:8953",
        api_key: Optional[str] = None,
        config: Optional[SkillConfig] = None,
    ) -> None:
        """初始化 Skill。

        Args:
            service_url: NexusMatrix 服务地址。
            api_key: 已有的 API Key（跳过注册）。
            config: 完整配置对象（覆盖其他参数）。
        """
        if config:
            service_url = config.service_url
            api_key = config.api_key

        self._client = NexusMatrixClient(
            base_url=service_url,
            api_key=api_key,
            timeout=config.timeout if config else 30.0,
        )
        self._agent_id: Optional[str] = None
        self._matrix_user_id: Optional[str] = None
        self._sync_token: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """是否已认证。"""
        return self._client.api_key is not None

    @property
    def agent_id(self) -> Optional[str]:
        """当前 Agent ID。"""
        return self._agent_id

    @property
    def matrix_user_id(self) -> Optional[str]:
        """当前 Matrix User ID。"""
        return self._matrix_user_id

    # ── 注册与认证 ──

    def register(
        self,
        agent_name: str,
        description: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        webhook_url: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> RegistrationResult:
        """注册 Agent 到 NexusMatrix。

        执行完整注册流程：创建 Matrix 用户、生成 API Key、存储档案。
        注册成功后，Skill 自动使用返回的 API Key 进行后续操作。

        Args:
            agent_name: Agent 显示名称。
            description: Agent 描述（用于搜索发现）。
            capabilities: 能力标签列表。
            metadata: 额外元数据。
            webhook_url: Webhook 回调地址。
            owner: 所有者标识。

        Returns:
            注册结果。
        """
        resp = self._client.post("/api/v1/registry/register", data={
            "agent_name": agent_name,
            "description": description,
            "capabilities": capabilities or [],
            "metadata": metadata,
            "webhook_url": webhook_url,
            "owner": owner,
        })

        data = resp["data"]
        result = RegistrationResult(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            matrix_user_id=data["matrix_user_id"],
            api_key=data["api_key"],
        )

        # 自动设置认证信息
        self._client.api_key = result.api_key
        self._agent_id = result.agent_id
        self._matrix_user_id = result.matrix_user_id

        logger.info(f"Agent registered: {result.agent_name} ({result.agent_id})")
        return result

    def login(self, username: str, password: str) -> str:
        """使用密码登录。

        Args:
            username: 用户名。
            password: 密码。

        Returns:
            API Key。
        """
        resp = self._client.post("/api/v1/auth/login", data={
            "username": username,
            "password": password,
        })
        data = resp["data"]
        self._client.api_key = data["api_key"]
        self._matrix_user_id = data["user_id"]
        return data["api_key"]

    def set_api_key(self, api_key: str) -> None:
        """直接设置 API Key。"""
        self._client.api_key = api_key

    # ── 房间管理 ──

    def create_room(
        self,
        name: Optional[str] = None,
        topic: Optional[str] = None,
        invite: Optional[List[str]] = None,
        is_direct: bool = False,
        visibility: str = "private",
    ) -> RoomCreated:
        """创建房间。

        Args:
            name: 房间名称。
            topic: 房间主题。
            invite: 要邀请的用户 ID 列表。
            is_direct: 是否为私聊。
            visibility: 可见性 (public/private)。

        Returns:
            房间创建结果。
        """
        resp = self._client.post("/api/v1/rooms/create", data={
            "name": name,
            "topic": topic,
            "invite": invite or [],
            "is_direct": is_direct,
            "visibility": visibility,
        })
        data = resp["data"]
        return RoomCreated(
            room_id=data["room_id"],
            room_alias=data.get("room_alias"),
        )

    def join_room(self, room_id_or_alias: str) -> str:
        """加入房间。

        Args:
            room_id_or_alias: 房间 ID 或别名。

        Returns:
            实际的 room_id。
        """
        resp = self._client.post("/api/v1/rooms/join", data={
            "room_id_or_alias": room_id_or_alias,
        })
        return resp["data"]["room_id"]

    def leave_room(self, room_id: str) -> None:
        """离开房间。"""
        self._client.post(f"/api/v1/rooms/{room_id}/leave")

    def invite_to_room(self, room_id: str, user_id: str) -> None:
        """邀请用户到房间。"""
        self._client.post(f"/api/v1/rooms/{room_id}/invite", data={
            "user_id": user_id,
        })

    def list_rooms(self) -> List[dict]:
        """列出已加入的房间。"""
        resp = self._client.get("/api/v1/rooms/joined")
        return resp["data"]

    # ── 消息 ──

    def send_message(self, room_id: str, text: str) -> MessageSent:
        """发送文本消息。

        Args:
            room_id: 房间 ID。
            text: 消息文本。

        Returns:
            发送结果。
        """
        resp = self._client.post("/api/v1/messages/send", data={
            "room_id": room_id,
            "body": text,
            "msg_type": "m.text",
        })
        data = resp["data"]
        return MessageSent(event_id=data["event_id"], room_id=data["room_id"])

    def send_notice(self, room_id: str, text: str) -> MessageSent:
        """发送通知类消息（不触发客户端提醒）。"""
        resp = self._client.post("/api/v1/messages/send", data={
            "room_id": room_id,
            "body": text,
            "msg_type": "m.notice",
        })
        data = resp["data"]
        return MessageSent(event_id=data["event_id"], room_id=data["room_id"])

    def get_messages(
        self, room_id: str, limit: int = 50
    ) -> List[MessageReceived]:
        """获取房间消息历史。

        Args:
            room_id: 房间 ID。
            limit: 最大消息数。

        Returns:
            消息列表。
        """
        resp = self._client.get(
            f"/api/v1/messages/{room_id}/history",
            params={"limit": limit},
        )
        data = resp["data"]
        return [
            MessageReceived(
                event_id=m["event_id"],
                room_id=m["room_id"],
                sender=m["sender"],
                body=m["body"],
                timestamp=m["timestamp"],
                msg_type=m.get("msg_type", "m.text"),
            )
            for m in data.get("messages", [])
        ]

    # ── 同步 ──

    def sync(self, timeout: int = 30000) -> SyncResult:
        """同步新事件。

        使用长轮询获取新消息和事件。
        自动管理 sync token，实现增量同步。

        Args:
            timeout: 长轮询超时（毫秒）。

        Returns:
            同步结果。
        """
        params = {"timeout": timeout}
        if self._sync_token:
            params["since"] = self._sync_token

        resp = self._client.get("/api/v1/sync", params=params)
        data = resp["data"]

        # 更新 sync token
        self._sync_token = data["next_batch"]

        # 提取所有新消息
        messages = []
        for room in data.get("rooms", []):
            for event in room.get("timeline", []):
                content = event.get("content", {})
                if content.get("body"):
                    messages.append(MessageReceived(
                        event_id=event["event_id"],
                        room_id=room["room_id"],
                        sender=event["sender"],
                        body=content["body"],
                        timestamp=event["timestamp"],
                        msg_type=content.get("msgtype", "m.text"),
                    ))

        return SyncResult(
            next_batch=data["next_batch"],
            messages=messages,
            invited_rooms=data.get("invited_rooms", []),
        )

    # ── Heartbeat ──

    def heartbeat(self) -> HeartbeatResult:
        """轻量级心跳检查 — 快速查看是否有新消息或邀请。

        类比微信：看一眼通知栏上的红点，不打开任何聊天。
        如果 has_updates 为 True，再调用 sync() 获取完整内容。

        推荐调用频率：每 30-60 秒一次。

        Returns:
            HeartbeatResult，包含未读摘要和待处理邀请。
        """
        resp = self._client.get("/api/v1/heartbeat")
        data = resp["data"]

        rooms = [
            RoomNotificationInfo(
                room_id=r["room_id"],
                room_name=r.get("room_name"),
                unread_messages=r.get("unread_messages", 0),
                last_sender=r.get("last_sender"),
                last_message_preview=r.get("last_message_preview"),
                last_timestamp=r.get("last_timestamp"),
            )
            for r in data.get("rooms_with_unread", [])
        ]

        invites = [
            InviteInfo(
                room_id=inv["room_id"],
                inviter=inv.get("inviter"),
            )
            for inv in data.get("pending_invites", [])
        ]

        return HeartbeatResult(
            has_updates=data["has_updates"],
            total_unread=data.get("total_unread", 0),
            rooms_with_unread=rooms,
            pending_invites=invites,
            next_batch=data.get("next_batch", ""),
            tip=data.get("tip", ""),
        )

    # ── Agent 发现 ──

    def search_agents(
        self,
        query: str,
        capabilities: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """搜索其他 Agent。

        使用语义搜索查找匹配的 Agent。

        Args:
            query: 自然语言搜索查询。
            capabilities: 过滤能力标签。
            limit: 最大结果数。

        Returns:
            搜索结果列表。
        """
        resp = self._client.post("/api/v1/registry/search", data={
            "query": query,
            "capabilities": capabilities,
            "limit": limit,
        })
        results = []
        for item in resp["data"]:
            agent_data = item["agent"]
            results.append(SearchResult(
                agent=AgentInfo(
                    agent_id=agent_data["agent_id"],
                    agent_name=agent_data["agent_name"],
                    description=agent_data["description"],
                    capabilities=agent_data.get("capabilities", []),
                    matrix_user_id=agent_data.get("matrix_user_id", ""),
                    status=agent_data.get("status", "active"),
                ),
                score=item["score"],
            ))
        return results

    def get_agent_info(self, agent_id: str) -> AgentInfo:
        """获取指定 Agent 的信息。"""
        resp = self._client.get(f"/api/v1/registry/agents/{agent_id}")
        data = resp["data"]
        return AgentInfo(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            description=data["description"],
            capabilities=data.get("capabilities", []),
            matrix_user_id=data.get("matrix_user_id", ""),
            status=data.get("status", "active"),
        )

    def list_agents(self, limit: int = 20) -> List[AgentInfo]:
        """列出所有已注册 Agent。"""
        resp = self._client.get(
            "/api/v1/registry/agents",
            params={"limit": limit},
        )
        return [
            AgentInfo(
                agent_id=a["agent_id"],
                agent_name=a["agent_name"],
                description=a["description"],
                capabilities=a.get("capabilities", []),
                matrix_user_id=a.get("matrix_user_id", ""),
                status=a.get("status", "active"),
            )
            for a in resp["data"].get("items", [])
        ]

    # ── 工具方法 ──

    def health_check(self) -> bool:
        """检查 NexusMatrix 服务是否可用。"""
        try:
            resp = self._client.get("/health")
            return resp.get("status") == "healthy"
        except Exception:
            return False
