"""
@file_name: feedback.py
@author: Bin Liang
@date: 2026-03-03
@description: 反馈系统数据模型

定义 Agent 反馈相关的请求/响应模型，
支持 Bug 报告、功能建议、错误日志上报、性能问题等类别。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FeedbackCategory(str, Enum):
    """反馈类别。"""

    BUG_REPORT = "bug_report"           # Bug 报告
    SUGGESTION = "suggestion"           # 功能建议
    FEATURE_REQUEST = "feature_request" # 功能需求（区别于建议，更具体的新功能请求）
    ERROR_LOG = "error_log"             # 错误日志上报
    PERFORMANCE = "performance"         # 性能问题


class FeedbackStatus(str, Enum):
    """反馈处理状态。"""

    PENDING = "pending"            # 待处理
    IN_PROGRESS = "in_progress"    # 处理中
    RESOLVED = "resolved"          # 已解决
    WONT_FIX = "wont_fix"          # 不修复


class SubmitFeedbackRequest(BaseModel):
    """反馈提交请求。"""

    category: FeedbackCategory = Field(
        ..., description="Feedback category"
    )
    title: str = Field(
        ..., min_length=1, max_length=200, description="Short summary of the feedback"
    )
    content: str = Field(
        ..., min_length=1, max_length=5000, description="Detailed description"
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional context (endpoint, error_code, request_body, etc.)",
    )


class ResolveFeedbackRequest(BaseModel):
    """反馈解决请求。"""

    resolution: str = Field(
        ..., min_length=1, max_length=2000, description="Resolution description"
    )
    status: FeedbackStatus = Field(
        FeedbackStatus.RESOLVED,
        description="Target status (resolved or wont_fix)",
    )


class FeedbackRecord(BaseModel):
    """反馈记录（完整实体）。"""

    feedback_id: str = Field(..., description="Unique feedback ID (fb_xxxxxxxx)")
    agent_id: str = Field(..., description="Submitter agent ID")
    agent_name: str = Field("", description="Submitter agent name")
    category: FeedbackCategory = Field(..., description="Feedback category")
    title: str = Field(..., description="Short summary")
    content: str = Field(..., description="Detailed description")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    status: FeedbackStatus = Field(..., description="Current status")
    resolution: Optional[str] = Field(None, description="Resolution note")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Last updated timestamp")


class FeedbackStats(BaseModel):
    """反馈统计摘要。"""

    total: int = Field(0, description="Total feedback count")
    pending: int = Field(0, description="Pending count")
    in_progress: int = Field(0, description="In-progress count")
    resolved: int = Field(0, description="Resolved count")
    wont_fix: int = Field(0, description="Won't-fix count")
