"""
@file_name: message_service.py
@author: Bin Liang
@date: 2026-03-03
@description: 消息服务

封装 Matrix 消息的发送、接收、历史记录查询等操作。
"""

from typing import Optional

from nio import (
    AsyncClient,
    RoomMessagesResponse,
    RoomSendResponse,
    RoomRedactResponse,
)
from loguru import logger

from nexus_matrix.models.messages import (
    MessageEvent,
    MessageHistory,
    SendMessageRequest,
    SendMessageResponse,
)


class MessageService:
    """消息服务。

    提供消息的发送、撤回、历史查询等功能。
    """

    async def send_message(
        self, client: AsyncClient, request: SendMessageRequest
    ) -> SendMessageResponse:
        """发送消息到指定房间。

        Args:
            client: 操作者的 Matrix 客户端。
            request: 发送消息请求。

        Returns:
            发送结果（包含 event_id）。
        """
        # 构造消息内容
        content = {
            "msgtype": request.msg_type.value,
            "body": request.body,
        }

        # 添加格式化内容（HTML）
        if request.formatted_body:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = request.formatted_body

        # 合并额外内容字段
        if request.extra_content:
            content.update(request.extra_content)

        response = await client.room_send(
            room_id=request.room_id,
            message_type="m.room.message",
            content=content,
        )

        if isinstance(response, RoomSendResponse):
            logger.debug(f"消息已发送到 {request.room_id}: {response.event_id}")
            return SendMessageResponse(
                event_id=response.event_id,
                room_id=request.room_id,
            )
        else:
            raise RuntimeError(f"Failed to send message: {response}")

    async def send_text(
        self, client: AsyncClient, room_id: str, text: str
    ) -> SendMessageResponse:
        """发送纯文本消息（便捷方法）。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            text: 文本内容。

        Returns:
            发送结果。
        """
        request = SendMessageRequest(room_id=room_id, body=text)
        return await self.send_message(client, request)

    async def send_notice(
        self, client: AsyncClient, room_id: str, text: str
    ) -> SendMessageResponse:
        """发送通知类型消息（不会触发客户端通知）。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            text: 文本内容。

        Returns:
            发送结果。
        """
        from nexus_matrix.models.messages import MessageType
        request = SendMessageRequest(
            room_id=room_id, body=text, msg_type=MessageType.NOTICE
        )
        return await self.send_message(client, request)

    async def redact_message(
        self, client: AsyncClient, room_id: str, event_id: str, reason: str = ""
    ) -> str:
        """撤回/删除消息。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            event_id: 要撤回的消息事件 ID。
            reason: 撤回原因。

        Returns:
            撤回事件的 event_id。
        """
        response = await client.room_redact(room_id, event_id, reason=reason)
        if isinstance(response, RoomRedactResponse):
            logger.debug(f"消息已撤回: {event_id}")
            return response.event_id
        else:
            raise RuntimeError(f"Failed to redact message: {response}")

    async def get_messages(
        self,
        client: AsyncClient,
        room_id: str,
        limit: int = 50,
        start: str = "",
        direction: str = "b",
    ) -> MessageHistory:
        """获取房间消息历史。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            limit: 最大消息数。
            start: 分页 token（为空则从最新开始）。
            direction: 方向，"b" = 向过去，"f" = 向未来。

        Returns:
            消息历史记录。
        """
        response = await client.room_messages(
            room_id=room_id,
            start=start,
            limit=limit,
            direction=direction,
        )

        if isinstance(response, RoomMessagesResponse):
            messages = []
            for event in response.chunk:
                # 只处理消息事件
                if hasattr(event, "body"):
                    messages.append(MessageEvent(
                        event_id=event.event_id,
                        room_id=room_id,
                        sender=event.sender,
                        body=getattr(event, "body", ""),
                        msg_type=getattr(event, "msgtype", "m.text") or "m.text",
                        formatted_body=getattr(event, "formatted_body", None),
                        timestamp=event.server_timestamp,
                        event_type="m.room.message",
                    ))

            return MessageHistory(
                room_id=room_id,
                messages=messages,
                start=response.start or "",
                end=response.end or "",
                has_more=len(messages) >= limit,
            )
        else:
            raise RuntimeError(f"Failed to get messages: {response}")

    async def send_typing(
        self, client: AsyncClient, room_id: str, typing: bool = True, timeout: int = 5000
    ) -> None:
        """发送正在输入状态。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            typing: 是否正在输入。
            timeout: 超时时间（毫秒）。
        """
        await client.room_typing(room_id, typing, timeout=timeout)

    async def mark_read(
        self, client: AsyncClient, room_id: str, event_id: str
    ) -> None:
        """标记消息为已读。

        Args:
            client: Matrix 客户端。
            room_id: 房间 ID。
            event_id: 已读到的消息事件 ID。
        """
        await client.room_read_markers(room_id, fully_read_event=event_id, read_event=event_id)
