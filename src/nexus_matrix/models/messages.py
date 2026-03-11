"""
@file_name: messages.py
@author: Bin Liang
@date: 2026-03-03
@description: 消息相关数据模型

定义消息发送、接收、历史记录查询等操作所需的数据结构。
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


class MessageType(str, Enum):
    """消息内容类型。"""

    TEXT = "m.text"
    NOTICE = "m.notice"
    IMAGE = "m.image"
    FILE = "m.file"
    EMOTE = "m.emote"


class SendMessageRequest(BaseModel):
    """发送消息请求。

    兼容多种字段名：
    - body / text / message / content 均可作为消息正文
    - room_id 为目标房间 ID

    content 字段同时兼容字符串和 Matrix 事件对象格式：
    - 字符串: "hello" → 直接作为消息正文
    - 对象: {"msgtype": "m.text", "body": "hello"} → 提取 body 字段
    """

    room_id: str = Field(..., description="Target room ID")
    body: Optional[str] = Field(None, description="Message body text")
    text: Optional[str] = Field(None, description="Alias for body")
    message: Optional[str] = Field(None, description="Alias for body")
    content: Optional[Union[str, Dict[str, Any]]] = Field(
        None, description="Alias for body (string or Matrix event object)"
    )
    msg_type: MessageType = Field(
        MessageType.TEXT, description="Message type"
    )
    formatted_body: Optional[str] = Field(
        None, description="HTML formatted body (optional)"
    )
    extra_content: Optional[Dict[str, Any]] = Field(
        None, description="Additional content fields"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_content(cls, values: Any) -> Any:
        """兼容 Agent 发送 Matrix 事件对象格式的 content。

        当 content 为 dict（如 {"msgtype": "m.text", "body": "hello"}）时，
        提取其中的 body 和 msgtype 字段，转换为扁平结构。
        """
        if isinstance(values, dict):
            content = values.get("content")
            if isinstance(content, dict):
                # 从 Matrix 事件对象中提取 body
                if "body" in content and not values.get("body"):
                    values["body"] = content["body"]
                # 提取 msgtype（如有）
                if "msgtype" in content and "msg_type" not in values:
                    values["msg_type"] = content["msgtype"]
                # 提取 formatted_body（如有）
                if "formatted_body" in content and not values.get("formatted_body"):
                    values["formatted_body"] = content["formatted_body"]
                # 清除 dict 类型的 content，避免类型校验失败
                values["content"] = None
        return values

    @model_validator(mode="after")
    def _resolve_body(self) -> "SendMessageRequest":
        """将 text / message / content 统一合并到 body。"""
        # 如果 content 仍为 dict（before validator 未能拦截），在此提取 body
        content_val = self.content
        if isinstance(content_val, dict):
            content_val = content_val.get("body")
            self.content = None
        resolved = self.body or self.text or self.message or content_val
        if not resolved:
            raise ValueError(
                "At least one of body, text, message, or content must be provided"
            )
        self.body = resolved
        return self


class SendTextRequest(BaseModel):
    """发送纯文本消息的简化请求。

    兼容 room_id 和 text / body / message 字段名。
    """

    room_id: str = Field(..., description="Target room ID")
    text: Optional[str] = Field(None, description="Message text")
    body: Optional[str] = Field(None, description="Alias for text")
    message: Optional[str] = Field(None, description="Alias for text")
    content: Optional[str] = Field(None, description="Alias for text (string content)")

    @model_validator(mode="after")
    def _resolve_text(self) -> "SendTextRequest":
        """将 body / message / content 统一合并到 text。"""
        resolved = self.text or self.body or self.message or self.content
        if not resolved:
            raise ValueError(
                "At least one of text, body, message, or content must be provided"
            )
        self.text = resolved
        return self


class SendMessageResponse(BaseModel):
    """发送消息响应。"""

    event_id: str = Field(..., description="Matrix event ID of the sent message")
    room_id: str = Field(..., description="Room the message was sent to")


class MessageEvent(BaseModel):
    """单条消息事件。"""

    event_id: str = Field(..., description="Unique event ID")
    room_id: str = Field(..., description="Room ID")
    sender: str = Field(..., description="Sender's Matrix user ID")
    body: str = Field("", description="Message body")
    msg_type: str = Field("m.text", description="Message type")
    formatted_body: Optional[str] = Field(None, description="HTML formatted body")
    timestamp: int = Field(..., description="Server timestamp (ms since epoch)")
    event_type: str = Field("m.room.message", description="Matrix event type")
    content: Optional[Dict[str, Any]] = Field(None, description="Full event content")


class MarkReadRequest(BaseModel):
    """标记已读请求（扁平接口）。

    兼容 Agent 不知道路径参数格式时使用的 body-only 请求。
    Agent 常调用 POST /messages/read 并将 room_id 放在 body 中。
    """

    room_id: str = Field(..., description="Target room ID")
    event_id: Optional[str] = Field(
        None, description="Event ID to mark as read (omit to mark all)"
    )


class MessageHistory(BaseModel):
    """消息历史记录。"""

    room_id: str = Field(..., description="Room ID")
    messages: List[MessageEvent] = Field(default_factory=list, description="Message list")
    start: str = Field("", description="Pagination start token")
    end: str = Field("", description="Pagination end token")
    has_more: bool = Field(False, description="Whether more messages exist")
