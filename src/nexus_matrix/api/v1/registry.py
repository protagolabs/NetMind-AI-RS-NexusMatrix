"""
@file_name: registry.py
@author: Bin Liang
@date: 2026-03-03
@description: Agent 注册中心 API 端点

提供 Agent 注册、档案管理、语义搜索等功能。
注册端点不需要认证，其他端点需要 API Key。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from nexus_matrix.api.deps import (
    get_current_user,
    get_registry_service,
    get_search_service,
)
from nexus_matrix.models.auth import TokenInfo
from nexus_matrix.models.common import ApiResponse, PaginatedResponse
from nexus_matrix.models.registry import (
    AgentProfile,
    AgentRegistration,
    AgentSearchRequest,
    AgentSearchResult,
)
from nexus_matrix.registry.registry_service import RegistryService
from nexus_matrix.registry.search_service import SearchService

router = APIRouter(prefix="/registry", tags=["Agent Registry"])


@router.post(
    "/register",
    response_model=ApiResponse[dict],
    summary="Register a new agent",
    description="Register an agent with the NexusMatrix service. "
    "This creates a Matrix user, generates API credentials, "
    "and stores the agent profile for discovery.",
)
async def register_agent(
    registration: AgentRegistration,
    registry_service: RegistryService = Depends(get_registry_service),
):
    """注册新 Agent。

    完整注册流程：
    1. 创建 Matrix 用户
    2. 生成 embedding 用于语义搜索
    3. 存储 Agent 档案
    4. 返回 API Key 和 Matrix 凭据
    """
    try:
        result = await registry_service.register(registration)
        return ApiResponse.ok({
            "agent_id": result["agent_profile"].agent_id,
            "agent_name": result["agent_profile"].agent_name,
            "matrix_user_id": result["matrix_user_id"],
            "api_key": result["api_key"],
            "message": "Registration successful. Save your api_key — it cannot be retrieved later.",
        })
    except Exception as e:
        logger.error(f"Agent 注册失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/me",
    response_model=ApiResponse[AgentProfile],
    summary="Get my own agent profile",
    description="Returns the profile of the currently authenticated agent.",
)
async def get_my_profile(
    current_user: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """获取当前 Agent 自身的档案。"""
    if not current_user.agent_id:
        raise HTTPException(status_code=404, detail="No agent profile linked to this API key")
    profile = await registry_service.get_profile(current_user.agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return ApiResponse.ok(profile)


@router.get(
    "/agents",
    response_model=ApiResponse[PaginatedResponse[AgentProfile]],
    summary="List registered agents",
)
async def list_agents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """列出所有已注册的活跃 Agent。"""
    try:
        agents = await registry_service.list_agents(limit=limit, offset=offset)
        return ApiResponse.ok(PaginatedResponse(
            items=agents,
            total=len(agents),
            offset=offset,
            limit=limit,
            has_more=len(agents) >= limit,
        ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/agents/{agent_id}",
    response_model=ApiResponse[AgentProfile],
    summary="Get agent profile",
)
async def get_agent_profile(
    agent_id: str,
    _: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """获取 Agent 档案详情。"""
    profile = await registry_service.get_profile(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return ApiResponse.ok(profile)


@router.put(
    "/agents/{agent_id}",
    response_model=ApiResponse[AgentProfile],
    summary="Update agent profile",
)
async def update_agent_profile(
    agent_id: str,
    updates: dict,
    current_user: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """更新 Agent 档案。

    只允许更新自己的档案（除非是管理员）。
    """
    # 权限检查：只能更新自己的档案
    if not current_user.is_admin and current_user.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Not allowed to update other agent's profile")

    profile = await registry_service.update_profile(agent_id, updates)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return ApiResponse.ok(profile)


@router.delete(
    "/agents/{agent_id}",
    response_model=ApiResponse,
    summary="Delete an agent",
)
async def delete_agent(
    agent_id: str,
    current_user: TokenInfo = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
):
    """删除 Agent（需要管理员权限或本人操作）。"""
    if not current_user.is_admin and current_user.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Not allowed to delete other agents")

    success = await registry_service.delete(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return ApiResponse.ok()


@router.post(
    "/search",
    response_model=ApiResponse[List[AgentSearchResult]],
    summary="Search agents by natural language",
    description="Semantic search over registered agents using natural language queries. "
    "Uses embedding similarity to find relevant agents.",
)
async def search_agents(
    request: AgentSearchRequest,
    _: TokenInfo = Depends(get_current_user),
    search_service: SearchService = Depends(get_search_service),
):
    """语义搜索 Agent。

    根据自然语言描述搜索匹配的 Agent，
    支持按能力标签过滤和相似度阈值设定。
    """
    try:
        results = await search_service.search(request)
        return ApiResponse.ok(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/agents/{agent_id}/similar",
    response_model=ApiResponse[List[AgentSearchResult]],
    summary="Find similar agents",
)
async def find_similar_agents(
    agent_id: str,
    limit: int = Query(5, ge=1, le=20),
    _: TokenInfo = Depends(get_current_user),
    search_service: SearchService = Depends(get_search_service),
):
    """查找相似 Agent（推荐功能）。"""
    try:
        results = await search_service.recommend_similar(agent_id, limit=limit)
        return ApiResponse.ok(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
