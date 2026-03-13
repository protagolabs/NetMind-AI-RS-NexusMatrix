"""
@file_name: room_service.py
@author: Bin Liang
@date: 2026-03-03
@description: 房间管理服务

封装 Matrix 房间的创建、加入、邀请、查询等操作。
通过 MatrixClientManager 获取对应 Agent 的客户端执行操作。
"""

from typing import List, Optional

from nio import (
    AsyncClient,
    JoinedRoomsResponse,
    RoomCreateResponse,
    RoomGetStateEventResponse,
    RoomInviteResponse,
    JoinResponse,
    RoomLeaveResponse,
    RoomKickResponse,
    RoomBanResponse,
    RoomUnbanResponse,
    RoomVisibility as NioRoomVisibility,
)
from nio.api import RoomPreset as NioRoomPreset
from loguru import logger

from nexus_matrix.core.matrix_client_manager import MatrixClientManager
from nexus_matrix.models.rooms import (
    CreateRoomRequest,
    CreateRoomResponse,
    RoomInfo,
    RoomMember,
    RoomPreset,
    RoomVisibility,
)


class RoomService:
    """房间管理服务。

    提供 Matrix 房间的完整生命周期管理：
    创建、加入、离开、邀请、踢人、封禁、查询信息等。
    """

    def __init__(self, client_manager: MatrixClientManager) -> None:
        self._client_manager = client_manager

    async def create_room(
        self, client: AsyncClient, request: CreateRoomRequest
    ) -> CreateRoomResponse:
        """创建新房间。

        Args:
            client: 操作者的 Matrix 客户端。
            request: 创建房间请求。

        Returns:
            创建结果（包含 room_id）。

        Raises:
            RuntimeError: 创建失败。
        """
        # 构造 nio 参数
        kwargs = {
            "name": request.name,
            "topic": request.topic,
            "invite": request.invite,
            "is_direct": request.is_direct,
        }

        # 映射 visibility
        if request.visibility == RoomVisibility.PUBLIC:
            kwargs["visibility"] = NioRoomVisibility.public
        else:
            kwargs["visibility"] = NioRoomVisibility.private

        # 映射 preset
        preset_map = {
            RoomPreset.PRIVATE_CHAT: NioRoomPreset.private_chat,
            RoomPreset.PUBLIC_CHAT: NioRoomPreset.public_chat,
            RoomPreset.TRUSTED_PRIVATE_CHAT: NioRoomPreset.trusted_private_chat,
        }
        nio_preset = preset_map.get(request.preset)
        if nio_preset:
            kwargs["preset"] = nio_preset

        if request.room_alias:
            kwargs["alias"] = request.room_alias

        if request.initial_state:
            kwargs["initial_state"] = request.initial_state

        response = await client.room_create(**kwargs)

        if isinstance(response, RoomCreateResponse):
            logger.info(f"房间已创建: {response.room_id}")
            alias = f"#{request.room_alias}:{self._client_manager.server_name}" if request.room_alias else None
            return CreateRoomResponse(room_id=response.room_id, room_alias=alias)
        else:
            raise RuntimeError(f"Failed to create room: {response}")

    async def join_room(self, client: AsyncClient, room_id_or_alias: str) -> str:
        """加入房间。

        Args:
            client: 操作者的 Matrix 客户端。
            room_id_or_alias: 房间 ID 或别名。

        Returns:
            实际的 room_id。
        """
        response = await client.join(room_id_or_alias)
        if isinstance(response, JoinResponse):
            logger.info(f"已加入房间: {response.room_id}")
            return response.room_id
        else:
            raise RuntimeError(f"Failed to join room: {response}")

    async def leave_room(self, client: AsyncClient, room_id: str) -> None:
        """离开房间。"""
        response = await client.room_leave(room_id)
        if isinstance(response, RoomLeaveResponse):
            logger.info(f"已离开房间: {room_id}")
        else:
            raise RuntimeError(f"Failed to leave room: {response}")

    async def invite_user(
        self, client: AsyncClient, room_id: str, user_id: str
    ) -> None:
        """邀请用户加入房间。"""
        response = await client.room_invite(room_id, user_id)
        if isinstance(response, RoomInviteResponse):
            logger.info(f"已邀请 {user_id} 到房间 {room_id}")
        else:
            raise RuntimeError(f"Failed to invite user: {response}")

    async def kick_user(
        self, client: AsyncClient, room_id: str, user_id: str, reason: str = ""
    ) -> None:
        """将用户踢出房间。"""
        response = await client.room_kick(room_id, user_id, reason=reason)
        if isinstance(response, RoomKickResponse):
            logger.info(f"已将 {user_id} 踢出房间 {room_id}")
        else:
            raise RuntimeError(f"Failed to kick user: {response}")

    async def ban_user(
        self, client: AsyncClient, room_id: str, user_id: str, reason: str = ""
    ) -> None:
        """封禁用户。"""
        response = await client.room_ban(room_id, user_id, reason=reason)
        if isinstance(response, RoomBanResponse):
            logger.info(f"已封禁 {user_id} 于房间 {room_id}")
        else:
            raise RuntimeError(f"Failed to ban user: {response}")

    async def unban_user(
        self, client: AsyncClient, room_id: str, user_id: str
    ) -> None:
        """解除封禁。"""
        response = await client.room_unban(room_id, user_id)
        if isinstance(response, RoomUnbanResponse):
            logger.info(f"已解封 {user_id} 于房间 {room_id}")
        else:
            raise RuntimeError(f"Failed to unban user: {response}")

    async def get_room_info(self, client: AsyncClient, room_id: str) -> RoomInfo:
        """获取房间详细信息。

        始终从 Matrix API（状态事件 + joined_members）获取数据，
        不依赖 nio 的内存缓存（client.rooms），避免服务重启后数据丢失。

        Args:
            client: 操作者的 Matrix 客户端。
            room_id: 房间 ID。

        Returns:
            房间详细信息。
        """
        # 并发获取所有字段，减少总耗时
        import asyncio
        name_task = self._get_state_field(client, room_id, "m.room.name", "name")
        topic_task = self._get_state_field(client, room_id, "m.room.topic", "topic")
        alias_task = self._get_state_field(client, room_id, "m.room.canonical_alias", "alias")
        creator_task = self._get_state_field(client, room_id, "m.room.create", "creator")
        encrypted_task = self._get_state_field(client, room_id, "m.room.encryption", "algorithm")
        member_count_task = self._get_member_count(client, room_id)

        name, topic, alias, creator, encryption_algo, member_count = await asyncio.gather(
            name_task, topic_task, alias_task, creator_task, encrypted_task, member_count_task,
        )

        return RoomInfo(
            room_id=room_id,
            name=name,
            topic=topic,
            canonical_alias=alias,
            member_count=member_count,
            creator=creator,
            is_encrypted=encryption_algo is not None,
        )

    async def _get_state_field(
        self, client: AsyncClient, room_id: str, event_type: str, field: str,
    ) -> Optional[str]:
        """从房间状态事件中获取指定字段。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            event_type: 状态事件类型（如 m.room.name）。
            field: content 中要提取的字段名。

        Returns:
            字段值，或 None。
        """
        try:
            response = await client.room_get_state_event(room_id, event_type, "")
            if isinstance(response, RoomGetStateEventResponse):
                return response.content.get(field)
        except Exception as e:
            logger.debug(f"无法获取房间 {room_id} 的 {event_type}: {e}")
        return None

    async def _get_member_count(self, client: AsyncClient, room_id: str) -> int:
        """通过 joined_members API 获取房间实际成员数。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。

        Returns:
            成员数量，失败时返回 0。
        """
        try:
            response = await client.joined_members(room_id)
            if hasattr(response, "members") and response.members:
                return len(response.members)
        except Exception as e:
            logger.debug(f"无法获取房间 {room_id} 的成员数: {e}")
        return 0

    async def get_joined_rooms(self, client: AsyncClient) -> List[RoomInfo]:
        """获取已加入的所有房间列表。

        通过 Matrix API 获取房间 ID 列表，再逐个查询详细信息。
        不依赖 nio 内存缓存。
        """
        response = await client.joined_rooms()
        if not isinstance(response, JoinedRoomsResponse):
            raise RuntimeError(f"获取已加入房间失败: {response}")

        rooms = []
        for room_id in response.rooms:
            info = await self.get_room_info(client, room_id)
            rooms.append(info)
        return rooms

    async def get_room_members(
        self, client: AsyncClient, room_id: str
    ) -> List[RoomMember]:
        """获取房间成员列表。

        nio joined_members 返回 JoinedMembersResponse，
        其 members 是 List[RoomMember(nio)]（nio 的 RoomMember 对象列表）。
        每个对象有 user_id, display_name, avatar_url 属性。
        """
        response = await client.joined_members(room_id)
        members = []
        if hasattr(response, "members") and response.members:
            for member in response.members:
                members.append(RoomMember(
                    user_id=getattr(member, "user_id", ""),
                    display_name=getattr(member, "display_name", None),
                    membership="join",
                    avatar_url=getattr(member, "avatar_url", None),
                ))
        else:
            logger.warning(f"获取房间成员失败: {response}")
        return members
