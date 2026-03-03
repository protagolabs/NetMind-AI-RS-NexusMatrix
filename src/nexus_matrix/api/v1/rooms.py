"""
@file_name: rooms.py
@author: Bin Liang
@date: 2026-03-03
@description: 房间管理 API 端点

提供房间的创建、加入、离开、邀请、查询等功能。
所有端点需要 API Key 认证。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from nio import AsyncClient

from nexus_matrix.api.deps import get_matrix_client, get_room_service
from nexus_matrix.core.room_service import RoomService
from nexus_matrix.models.common import ApiResponse
from nexus_matrix.models.rooms import (
    CreateRoomRequest,
    CreateRoomResponse,
    InviteRequest,
    JoinRoomRequest,
    RoomInfo,
    RoomMember,
)

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.post(
    "/create",
    response_model=ApiResponse[CreateRoomResponse],
    summary="Create a new room",
)
async def create_room(
    request: CreateRoomRequest,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """创建新房间。"""
    try:
        result = await room_service.create_room(client, request)
        return ApiResponse.ok(result)
    except Exception as e:
        logger.error(f"创建房间失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/join",
    response_model=ApiResponse[dict],
    summary="Join a room",
)
async def join_room(
    request: JoinRoomRequest,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """加入房间。"""
    try:
        room_id = await room_service.join_room(client, request.room_id_or_alias)
        return ApiResponse.ok({"room_id": room_id})
    except Exception as e:
        logger.error(f"加入房间失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/leave",
    response_model=ApiResponse,
    summary="Leave a room",
)
async def leave_room(
    room_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """离开房间。"""
    try:
        await room_service.leave_room(client, room_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/invite",
    response_model=ApiResponse,
    summary="Invite a user to a room",
)
async def invite_user(
    room_id: str,
    request: InviteRequest,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """邀请用户到房间。"""
    try:
        await room_service.invite_user(client, room_id, request.user_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/kick",
    response_model=ApiResponse,
    summary="Kick a user from a room",
)
async def kick_user(
    room_id: str,
    request: InviteRequest,
    reason: str = "",
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """将用户踢出房间。"""
    try:
        await room_service.kick_user(client, room_id, request.user_id, reason)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/ban",
    response_model=ApiResponse,
    summary="Ban a user from a room",
)
async def ban_user(
    room_id: str,
    request: InviteRequest,
    reason: str = "",
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """封禁用户。"""
    try:
        await room_service.ban_user(client, room_id, request.user_id, reason)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/unban",
    response_model=ApiResponse,
    summary="Unban a user from a room",
)
async def unban_user(
    room_id: str,
    request: InviteRequest,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """解除封禁。"""
    try:
        await room_service.unban_user(client, room_id, request.user_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/joined",
    response_model=ApiResponse[List[RoomInfo]],
    summary="List all joined rooms",
)
async def list_joined_rooms(
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """列出所有已加入的房间。"""
    try:
        rooms = await room_service.get_joined_rooms(client)
        return ApiResponse.ok(rooms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/list",
    response_model=ApiResponse[List[RoomInfo]],
    summary="List all joined rooms (alias for /joined)",
)
async def list_rooms_alias(
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """列出所有已加入的房间（/joined 的别名）。"""
    try:
        rooms = await room_service.get_joined_rooms(client)
        return ApiResponse.ok(rooms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{room_id}/info",
    response_model=ApiResponse[RoomInfo],
    summary="Get room info (alias)",
)
async def get_room_info_alias(
    room_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """获取房间详情（/rooms/{room_id} 的别名）。"""
    try:
        info = await room_service.get_room_info(client, room_id)
        return ApiResponse.ok(info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{room_id}/members",
    response_model=ApiResponse[List[RoomMember]],
    summary="Get room members",
)
async def get_room_members(
    room_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """获取房间成员列表。"""
    try:
        members = await room_service.get_room_members(client, room_id)
        return ApiResponse.ok(members)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{room_id}",
    response_model=ApiResponse[RoomInfo],
    summary="Get room info",
)
async def get_room_info(
    room_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    room_service: RoomService = Depends(get_room_service),
):
    """获取房间详情。"""
    try:
        info = await room_service.get_room_info(client, room_id)
        return ApiResponse.ok(info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
