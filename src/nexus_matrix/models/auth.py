"""
@file_name: auth.py
@author: Bin Liang
@date: 2026-03-03
@description: 认证相关数据模型

定义登录、注册、Token 等认证流程所需的请求/响应模型。
"""

from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """Agent 注册请求。

    新 Agent 通过此接口在 NexusMatrix 注册，
    系统会在 Matrix homeserver 上创建对应用户。
    """

    username: str = Field(
        ..., min_length=3, max_length=50,
        description="Desired username (will become Matrix localpart)",
    )
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Password for Matrix account",
    )
    display_name: Optional[str] = Field(
        None, max_length=100,
        description="Display name for the agent",
    )


class RegisterResponse(BaseModel):
    """注册响应。"""

    user_id: str = Field(..., description="Full Matrix user ID (e.g., @bot:server)")
    api_key: str = Field(..., description="API key for authenticating with NexusMatrix service")
    access_token: str = Field(..., description="Matrix access token")
    device_id: str = Field(..., description="Matrix device ID")


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., description="Matrix localpart or full user ID")
    password: str = Field(..., description="Account password")


class LoginResponse(BaseModel):
    """登录响应。"""

    user_id: str = Field(..., description="Full Matrix user ID")
    access_token: str = Field(..., description="Matrix access token")
    device_id: str = Field(..., description="Matrix device ID")
    api_key: str = Field(..., description="NexusMatrix API key")


class TokenInfo(BaseModel):
    """Token/API Key 校验结果。"""

    user_id: str = Field(..., description="Associated Matrix user ID")
    agent_id: Optional[str] = Field(None, description="Associated agent ID if registered")
    is_admin: bool = Field(False, description="Whether this is an admin token")
