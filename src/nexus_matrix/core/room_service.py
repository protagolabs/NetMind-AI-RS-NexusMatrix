"""
@file_name: room_service.py
@author: Bin Liang
@date: 2026-03-03
@description: Room management service.

Wraps Matrix room operations: create, join, invite, query, etc.
Uses MatrixClientManager to obtain the corresponding Agent's client.
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
    """Room management service.

    Provides full lifecycle management for Matrix rooms:
    create, join, leave, invite, kick, ban, query info, etc.
    """

    def __init__(self, client_manager: MatrixClientManager) -> None:
        self._client_manager = client_manager

    async def create_room(
        self, client: AsyncClient, request: CreateRoomRequest
    ) -> CreateRoomResponse:
        """Create a new room.

        Args:
            client: The operator's Matrix client.
            request: Room creation request.

        Returns:
            Creation result (contains room_id).

        Raises:
            RuntimeError: If creation fails.
        """
        # Build nio kwargs
        kwargs = {
            "name": request.name,
            "topic": request.topic,
            "invite": request.invite,
            "is_direct": request.is_direct,
        }

        # Map visibility
        if request.visibility == RoomVisibility.PUBLIC:
            kwargs["visibility"] = NioRoomVisibility.public
        else:
            kwargs["visibility"] = NioRoomVisibility.private

        # Map preset
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
            logger.info(f"Room created: {response.room_id}")
            alias = f"#{request.room_alias}:{self._client_manager.server_name}" if request.room_alias else None
            return CreateRoomResponse(room_id=response.room_id, room_alias=alias)
        else:
            raise RuntimeError(f"Failed to create room: {response}")

    async def join_room(self, client: AsyncClient, room_id_or_alias: str) -> str:
        """Join a room.

        Args:
            client: The operator's Matrix client.
            room_id_or_alias: Room ID or alias.

        Returns:
            The actual room_id.
        """
        response = await client.join(room_id_or_alias)
        if isinstance(response, JoinResponse):
            logger.info(f"Joined room: {response.room_id}")
            return response.room_id
        else:
            raise RuntimeError(f"Failed to join room: {response}")

    async def leave_room(self, client: AsyncClient, room_id: str) -> None:
        """Leave a room."""
        response = await client.room_leave(room_id)
        if isinstance(response, RoomLeaveResponse):
            logger.info(f"Left room: {room_id}")
        else:
            raise RuntimeError(f"Failed to leave room: {response}")

    async def invite_user(
        self, client: AsyncClient, room_id: str, user_id: str
    ) -> None:
        """Invite a user to a room."""
        response = await client.room_invite(room_id, user_id)
        if isinstance(response, RoomInviteResponse):
            logger.info(f"Invited {user_id} to room {room_id}")
        else:
            raise RuntimeError(f"Failed to invite user: {response}")

    async def kick_user(
        self, client: AsyncClient, room_id: str, user_id: str, reason: str = ""
    ) -> None:
        """Kick a user from a room."""
        response = await client.room_kick(room_id, user_id, reason=reason)
        if isinstance(response, RoomKickResponse):
            logger.info(f"Kicked {user_id} from room {room_id}")
        else:
            raise RuntimeError(f"Failed to kick user: {response}")

    async def ban_user(
        self, client: AsyncClient, room_id: str, user_id: str, reason: str = ""
    ) -> None:
        """Ban a user from a room."""
        response = await client.room_ban(room_id, user_id, reason=reason)
        if isinstance(response, RoomBanResponse):
            logger.info(f"Banned {user_id} from room {room_id}")
        else:
            raise RuntimeError(f"Failed to ban user: {response}")

    async def unban_user(
        self, client: AsyncClient, room_id: str, user_id: str
    ) -> None:
        """Unban a user from a room."""
        response = await client.room_unban(room_id, user_id)
        if isinstance(response, RoomUnbanResponse):
            logger.info(f"Unbanned {user_id} from room {room_id}")
        else:
            raise RuntimeError(f"Failed to unban user: {response}")

    async def get_room_info(self, client: AsyncClient, room_id: str) -> RoomInfo:
        """Get detailed room information.

        Always fetches from Matrix API (state events + joined_members),
        never relies on nio's in-memory cache (client.rooms) which is
        lost on server restart.

        Args:
            client: The operator's Matrix client.
            room_id: Room ID.

        Returns:
            Detailed room information.
        """
        # Fetch all fields concurrently to minimize total latency
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
        """Extract a single field from a room state event.

        Args:
            client: Matrix client.
            room_id: Room ID.
            event_type: State event type (e.g. m.room.name).
            field: Key to extract from the event content.

        Returns:
            The field value, or None if unavailable.
        """
        try:
            response = await client.room_get_state_event(room_id, event_type, "")
            if isinstance(response, RoomGetStateEventResponse):
                return response.content.get(field)
        except Exception as e:
            logger.debug(f"Failed to get {event_type} for room {room_id}: {e}")
        return None

    async def _get_member_count(self, client: AsyncClient, room_id: str) -> int:
        """Get the actual member count via the joined_members API.

        Args:
            client: Matrix client.
            room_id: Room ID.

        Returns:
            Number of joined members, or 0 on failure.
        """
        try:
            response = await client.joined_members(room_id)
            if hasattr(response, "members") and response.members:
                return len(response.members)
        except Exception as e:
            logger.debug(f"Failed to get member count for room {room_id}: {e}")
        return 0

    async def get_joined_rooms(self, client: AsyncClient) -> List[RoomInfo]:
        """List all joined rooms.

        Fetches room IDs via Matrix API, then queries detailed info for each.
        Does not rely on nio's in-memory cache.
        """
        response = await client.joined_rooms()
        if not isinstance(response, JoinedRoomsResponse):
            raise RuntimeError(f"Failed to list joined rooms: {response}")

        rooms = []
        for room_id in response.rooms:
            info = await self.get_room_info(client, room_id)
            rooms.append(info)
        return rooms

    async def get_room_members(
        self, client: AsyncClient, room_id: str
    ) -> List[RoomMember]:
        """Get the list of joined members in a room.

        Uses nio's joined_members API which returns JoinedMembersResponse
        with a list of member objects (user_id, display_name, avatar_url).
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
            logger.warning(f"Failed to get room members: {response}")
        return members
