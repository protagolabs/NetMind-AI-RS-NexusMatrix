"""
@file_name: auth.py
@author: Bin Liang
@date: 2026-03-03
@description: 认证相关 API 端点

提供用户注册、登录、Token 校验等认证功能。
注册端点不需要认证（公开），其他端点需要 API Key。
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from nexus_matrix.api.deps import get_auth_service, get_current_user
from nexus_matrix.core.auth_service import AuthService
from nexus_matrix.models.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    TokenInfo,
)
from nexus_matrix.models.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=ApiResponse[RegisterResponse],
    summary="Register a new Matrix user",
    description="Create a new Matrix user account and get API credentials. "
    "This endpoint does not require authentication.",
)
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """注册新用户。

    在 Matrix homeserver 上创建用户并返回 API Key。
    此端点无需认证。
    """
    try:
        result = await auth_service.register_agent(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
        )
        return ApiResponse.ok(result)
    except Exception as e:
        logger.error(f"用户注册失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse],
    summary="Login with username and password",
)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """使用用户名密码登录。"""
    try:
        result = await auth_service.login(request.username, request.password)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get(
    "/verify",
    response_model=ApiResponse[TokenInfo],
    summary="Verify API key and get user info",
)
async def verify_token(
    current_user: TokenInfo = Depends(get_current_user),
):
    """校验 API Key 并返回用户信息。"""
    return ApiResponse.ok(current_user)
