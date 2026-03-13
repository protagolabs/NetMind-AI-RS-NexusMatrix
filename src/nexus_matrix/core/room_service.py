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

        从客户端本地缓存和 Matrix API 中收集房间元数据。
        creator 通过 m.room.create 状态事件获取（nio.MatrixRoom 没有 creator 属性）。

        Args:
            client: 操作者的 Matrix 客户端。
            room_id: 房间 ID。

        Returns:
            房间详细信息。
        """
        # 获取 creator：从 m.room.create 状态事件中提取
        creator = await self._get_room_creator(client, room_id)

        room = client.rooms.get(room_id)
        if room:
            return RoomInfo(
                room_id=room_id,
                name=room.name,
                topic=room.topic,
                canonical_alias=room.canonical_alias,
                member_count=room.member_count,
                creator=creator,
                is_encrypted=room.encrypted,
            )

        # 本地缓存无数据，通过状态事件获取 name 和 topic
        name = await self._get_room_state_field(client, room_id, "m.room.name", "name")
        topic = await self._get_room_state_field(client, room_id, "m.room.topic", "topic")
        return RoomInfo(room_id=room_id, name=name, topic=topic, creator=creator)

    async def _get_room_state_field(
        self, client: AsyncClient, room_id: str, event_type: str, field: str,
    ) -> Optional[str]:
        """从房间状态事件中获取指定字段。

        当 nio 本地缓存无数据时（如服务重启后），通过状态事件 API 获取房间元数据。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            event_type: 状态事件类型（如 m.room.name）。
            field: 要提取的字段名。

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

    async def _get_room_creator(
        self, client: AsyncClient, room_id: str
    ) -> Optional[str]:
        """从 m.room.create 状态事件获取房间创建者。

        nio.MatrixRoom 没有 creator 属性，必须通过状态事件 API 获取。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。

        Returns:
            创建者的 Matrix user ID，或 None。
        """
        try:
            response = await client.room_get_state_event(
                room_id, "m.room.create", ""
            )
            if isinstance(response, RoomGetStateEventResponse):
                # m.room.create 事件的 content 包含 creator 字段
                return response.content.get("creator")
        except Exception as e:
            logger.debug(f"无法获取房间 {room_id} 的 creator: {e}")
        return None

    async def get_joined_rooms(self, client: AsyncClient) -> List[RoomInfo]:
        """获取已加入的所有房间列表。"""
        response = await client.joined_rooms()
        if not isinstance(response, JoinedRoomsResponse):
            logger.warning(f"获取已加入房间失败: {response}")
            # 回退：从客户端本地缓存获取
            return [
                await self.get_room_info(client, room_id)
                for room_id in client.rooms
            ]
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
