"""
@file_name: feedback.py
@author: Bin Liang
@date: 2026-03-03
@description: 反馈系统 API 端点

提供 Agent 反馈提交、查询、解决等功能。
巡检脚本通过 /feedback/unresolved 端点获取待处理反馈。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from nexus_matrix.api.deps import get_current_user, get_feedback_repo
from nexus_matrix.models.auth import TokenInfo
from nexus_matrix.models.common import ApiResponse, PaginatedResponse
from nexus_matrix.models.feedback import (
    FeedbackRecord,
    FeedbackStats,
    FeedbackStatus,
    ResolveFeedbackRequest,
    SubmitFeedbackRequest,
)
from nexus_matrix.storage.repositories.feedback_repo import FeedbackRepository
from nexus_matrix.utils.security import generate_id

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post(
    "",
    response_model=ApiResponse[FeedbackRecord],
    summary="Submit feedback",
    description="Submit a bug report, suggestion, error log, or performance issue.",
)
async def submit_feedback(
    request: SubmitFeedbackRequest,
    current_user: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """提交反馈。

    Agent 可以提交各类反馈（Bug、建议、错误日志、性能问题），
    反馈会被存储到数据库中供巡检脚本处理。
    """
    try:
        feedback_id = generate_id("fb")
        record = await feedback_repo.create(
            feedback_id=feedback_id,
            agent_id=current_user.agent_id or current_user.user_id,
            agent_name=current_user.user_id,
            category=request.category,
            title=request.title,
            content=request.content,
            context=request.context,
        )
        logger.info(
            f"反馈已提交: {feedback_id} by {current_user.user_id} "
            f"[{request.category.value}] {request.title}"
        )
        return ApiResponse.ok(record)
    except Exception as e:
        logger.error(f"反馈提交失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "",
    response_model=ApiResponse[PaginatedResponse[FeedbackRecord]],
    summary="List my feedback",
    description="List feedback submitted by the current agent.",
)
async def list_my_feedback(
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """列出当前 Agent 提交的反馈。"""
    try:
        agent_id = current_user.agent_id or current_user.user_id
        items = await feedback_repo.list_by_agent(agent_id, limit=limit, offset=offset)
        total = await feedback_repo.count_by_agent(agent_id)
        return ApiResponse.ok(PaginatedResponse(
            items=items,
            total=total,
            offset=offset,
            limit=limit,
            has_more=(offset + limit) < total,
        ))
    except Exception as e:
        logger.error(f"反馈列表获取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/unresolved",
    response_model=ApiResponse[List[FeedbackRecord]],
    summary="List unresolved feedback",
    description="List all pending and in-progress feedback. "
    "Designed for the auto-patrol script to fetch work items.",
)
async def list_unresolved_feedback(
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    _: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """列出所有未解决反馈（供巡检脚本使用）。"""
    try:
        items = await feedback_repo.list_unresolved(limit=limit)
        return ApiResponse.ok(items)
    except Exception as e:
        logger.error(f"未解决反馈列表获取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stats",
    response_model=ApiResponse[FeedbackStats],
    summary="Feedback statistics",
    description="Get aggregated feedback counts grouped by status.",
)
async def get_feedback_stats(
    _: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """获取反馈统计数据。"""
    try:
        counts = await feedback_repo.count_by_status()
        stats = FeedbackStats(
            total=sum(counts.values()),
            pending=counts.get(FeedbackStatus.PENDING.value, 0),
            in_progress=counts.get(FeedbackStatus.IN_PROGRESS.value, 0),
            resolved=counts.get(FeedbackStatus.RESOLVED.value, 0),
            wont_fix=counts.get(FeedbackStatus.WONT_FIX.value, 0),
        )
        return ApiResponse.ok(stats)
    except Exception as e:
        logger.error(f"反馈统计获取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{feedback_id}",
    response_model=ApiResponse[FeedbackRecord],
    summary="Get feedback detail",
    description="Get a single feedback record by its ID.",
)
async def get_feedback(
    feedback_id: str,
    _: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """获取反馈详情。"""
    record = await feedback_repo.get_by_id(feedback_id)
    if not record:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return ApiResponse.ok(record)


@router.put(
    "/{feedback_id}/resolve",
    response_model=ApiResponse[FeedbackRecord],
    summary="Resolve feedback",
    description="Mark a feedback item as resolved or won't-fix with a resolution note.",
)
async def resolve_feedback(
    feedback_id: str,
    request: ResolveFeedbackRequest,
    current_user: TokenInfo = Depends(get_current_user),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repo),
):
    """标记反馈为已解决。

    允许设置状态为 resolved 或 wont_fix，
    并附带解决说明。
    """
    # 校验目标状态只能是终态
    if request.status not in (FeedbackStatus.RESOLVED, FeedbackStatus.WONT_FIX):
        raise HTTPException(
            status_code=400,
            detail="Status must be 'resolved' or 'wont_fix'",
        )

    # 检查反馈是否存在
    existing = await feedback_repo.get_by_id(feedback_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Feedback not found")

    record = await feedback_repo.update_status(
        feedback_id=feedback_id,
        status=request.status,
        resolution=request.resolution,
    )
    logger.info(
        f"反馈已解决: {feedback_id} -> {request.status.value} "
        f"by {current_user.user_id}"
    )
    return ApiResponse.ok(record)
