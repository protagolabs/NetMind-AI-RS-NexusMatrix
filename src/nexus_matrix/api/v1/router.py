"""
@file_name: router.py
@author: Bin Liang
@date: 2026-03-03
@description: API v1 路由聚合

将所有 v1 端点路由聚合到一个统一的 router 中。
"""

from fastapi import APIRouter, Depends, HTTPException

from nexus_matrix.api.deps import get_current_user, get_registry_service
from nexus_matrix.api.v1.auth import router as auth_router
from nexus_matrix.api.v1.rooms import router as rooms_router
from nexus_matrix.api.v1.messages import router as messages_router
from nexus_matrix.api.v1.sync import router as sync_router
from nexus_matrix.api.v1.registry import router as registry_router
from nexus_matrix.api.v1.feedback import router as feedback_router
from nexus_matrix.api.v1.heartbeat import router as heartbeat_router
from nexus_matrix.models.auth import TokenInfo
from nexus_matrix.models.common import ApiResponse
from nexus_matrix.models.registry import AgentProfile
from nexus_matrix.registry.registry_service import RegistryService

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(rooms_router)
router.include_router(messages_router)
router.include_router(sync_router)
router.include_router(registry_router)
router.include_router(feedback_router)
router.include_router(heartbeat_router)


# ── Agent 尝试使用的便捷路径别名 ──

@router.get(
    "/agents/me",
    response_model=ApiResponse[AgentProfile],
    summary="Get my own agent profile (alias for /registry/me)",
    tags=["Agent Registry"],
)
async def agents_me_alias(
    current_user: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """获取当前 Agent 自身的档案（/registry/me 的便捷别名）。"""
    if not current_user.agent_id:
        raise HTTPException(status_code=404, detail="No agent profile linked to this API key")
    profile = await registry_service.get_profile(current_user.agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return ApiResponse.ok(profile)
