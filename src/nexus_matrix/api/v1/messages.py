"""
@file_name: messages.py
@author: Bin Liang
@date: 2026-03-03
@description: 消息 API 端点

提供消息发送、撤回、历史查询等功能。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from nio import AsyncClient

from nexus_matrix.api.deps import get_matrix_client, get_message_service
from nexus_matrix.core.message_service import MessageService
from nexus_matrix.models.common import ApiResponse
from nexus_matrix.models.messages import (
    MarkReadRequest,
    MessageHistory,
    SendMessageRequest,
    SendMessageResponse,
    SendTextRequest,
)

router = APIRouter(prefix="/messages", tags=["Messages"])


def _resolve_room_id(room_id: str, client: AsyncClient) -> str:
    """清理、验证并解析 room_id 路径参数。

    处理 Agent 常见的错误用法：
    - 使用房间名称（如 "Alliance HQ"）代替 room_id → 自动从缓存查找匹配的房间
    - URL 路径中多余的反斜杠转义（如 "\\!roomId:server" → "!roomId:server"）

    Args:
        room_id: 原始 room_id 路径参数（可能是 room_id 或房间名称）。
        client: 当前用户的 Matrix 客户端，用于按名称查找房间。

    Returns:
        解析后的合法 Matrix room_id。

    Raises:
        HTTPException: 400，当无法解析为合法的 Matrix room ID。
    """
    # 去除前导反斜杠（Agent 常将 ! 转义为 \!）
    cleaned = room_id.lstrip("\\")

    # 如果已经是合法的 Matrix room ID 格式，直接返回
    if cleaned.startswith("!") and ":" in cleaned:
        return cleaned

    # 尝试按房间名称从客户端缓存中查找
    for rid, room in client.rooms.items():
        if room.name == room_id or room.canonical_alias == room_id:
            logger.info(f"房间名称 '{room_id}' 已解析为 room_id: {rid}")
            return rid

    raise HTTPException(
        status_code=400,
        detail=(
            f"Invalid room_id: '{room_id}'. "
            "Matrix room IDs must start with '!' and contain ':', "
            "e.g. '!abc123:localhost'. "
            "Room name lookup found no match either. "
            "Use GET /api/v1/rooms to find your room IDs."
        ),
    )


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
    room_id = _resolve_room_id(room_id, client)
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
    room_id = _resolve_room_id(room_id, client)
    try:
        history = await message_service.get_messages(
            client, room_id, limit=limit, start=start, direction=direction
        )
        return ApiResponse.ok(history)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    room_id = _resolve_room_id(room_id, client)
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
    room_id = _resolve_room_id(room_id, client)
    try:
        await message_service.mark_read(client, room_id, event_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{room_id}/read",
    response_model=ApiResponse,
    summary="Mark all messages in a room as read",
)
async def mark_all_read(
    room_id: str,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """标记房间内所有消息为已读。

    获取房间最新一条消息的 event_id，然后标记已读到该消息。
    Agent 常在不知道具体 event_id 时使用此接口。
    """
    room_id = _resolve_room_id(room_id, client)
    try:
        # 获取最新的一条消息
        history = await message_service.get_messages(client, room_id, limit=1)
        if history.messages:
            latest_event_id = history.messages[0].event_id
            await message_service.mark_read(client, room_id, latest_event_id)
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 扁平别名端点 ──
# Agent 经常猜测 URL 格式，尝试 POST /messages/read 或 /messages/mark-read
# 而非正确的 POST /messages/{room_id}/read。
# 以下别名端点接受 room_id 放在请求体中，委托给上面的核心逻辑。


async def _handle_mark_read_flat(
    request: MarkReadRequest,
    client: AsyncClient,
    message_service: MessageService,
) -> ApiResponse:
    """扁平标记已读的公共逻辑。

    根据 request 中是否包含 event_id 决定标记单条还是全部已读。

    Args:
        request: 标记已读请求（含 room_id、可选 event_id）。
        client: Matrix 客户端。
        message_service: 消息服务实例。

    Returns:
        标准 API 响应。
    """
    room_id = _resolve_room_id(request.room_id, client)
    try:
        if request.event_id:
            await message_service.mark_read(client, room_id, request.event_id)
        else:
            history = await message_service.get_messages(client, room_id, limit=1)
            if history.messages:
                await message_service.mark_read(
                    client, room_id, history.messages[0].event_id
                )
        return ApiResponse.ok()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/read",
    response_model=ApiResponse,
    summary="Mark messages as read (flat alias)",
)
async def mark_read_flat(
    request: MarkReadRequest,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """标记已读 — 扁平别名。

    接受 room_id 在请求体中，兼容 Agent 常见的
    POST /messages/read 调用模式。
    """
    return await _handle_mark_read_flat(request, client, message_service)


@router.post(
    "/mark-read",
    response_model=ApiResponse,
    summary="Mark messages as read (alias: mark-read)",
)
async def mark_read_alias_dash(
    request: MarkReadRequest,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """标记已读 — mark-read 别名。"""
    return await _handle_mark_read_flat(request, client, message_service)


@router.post(
    "/mark_read",
    response_model=ApiResponse,
    summary="Mark messages as read (alias: mark_read)",
)
async def mark_read_alias_underscore(
    request: MarkReadRequest,
    client: AsyncClient = Depends(get_matrix_client),
    message_service: MessageService = Depends(get_message_service),
):
    """标记已读 — mark_read 别名。"""
    return await _handle_mark_read_flat(request, client, message_service)
