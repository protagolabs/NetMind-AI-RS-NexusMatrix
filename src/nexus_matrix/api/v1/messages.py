"""
@file_name: messages.py
@author: Bin Liang
@date: 2026-03-03
@description: 消息 API 端点

提供消息发送、撤回、历史查询等功能。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from nio import AsyncClient

from nexus_matrix.api.deps import get_matrix_client, get_message_service
from nexus_matrix.core.message_service import MessageService
from nexus_matrix.models.common import ApiResponse
from nexus_matrix.models.messages import (
    MessageHistory,
    SendMessageRequest,
    SendMessageResponse,
    SendTextRequest,
)

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post(
    "/send",
    response_model=ApiResponse[SendMessageResponse],
    summary="Send a message to a room",
)
async def send_message(
    request: SendMessageRequest,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """发送消息到指定房间。"""
    try:
        result = await message_service.send_message(client, request)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/send/text",
    response_model=ApiResponse[SendMessageResponse],
    summary="Send a text message (simplified)",
)
async def send_text_message(
    request: SendTextRequest,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """发送纯文本消息（简便接口）。"""
    try:
        result = await message_service.send_text(client, request.room_id, request.text)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{room_id}/{event_id}",
    response_model=ApiResponse[dict],
    summary="Redact (delete) a message",
)
async def redact_message(
    room_id: str,
    event_id: str,
    reason: str = "",
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """撤回/删除消息。"""
    try:
        redact_id = await message_service.redact_message(
            client, room_id, event_id, reason
        )
        return ApiResponse.ok({"redact_event_id": redact_id})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{room_id}/history",
    response_model=ApiResponse[MessageHistory],
    summary="Get message history for a room",
)
async def get_message_history(
    room_id: str,
    limit: int = Query(50, ge=1, le=500, description="Max messages to return"),
    start: str = Query("", description="Pagination token"),
    direction: str = Query("b", description="Direction: 'b' for backward, 'f' for forward"),
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """获取房间消息历史。"""
    try:
        history = await message_service.get_messages(
            client, room_id, limit=limit, start=start, direction=direction
        )
        return ApiResponse.ok(history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{room_id}/typing",
    response_model=ApiResponse,
    summary="Send typing notification",
)
async def send_typing(
    room_id: str,
    typing: bool = True,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """发送正在输入状态。"""
    try:
        await message_service.send_typing(client, room_id, typing)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/read/{event_id}",
    response_model=ApiResponse,
    summary="Mark a message as read",
)
async def mark_read(
    room_id: str,
    event_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """标记消息为已读。"""
    try:
        await message_service.mark_read(client, room_id, event_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
