"""
@file_name: registry.py
@author: Bin Liang
@date: 2026-03-03
@description: Agent 注册中心数据模型

定义 Agent 注册、档案、搜索等功能所需的数据结构。
每个 Agent 在使用 NexusMatrix 服务前必须先注册。
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class AgentStatus(str, Enum):
    """Agent 状态。"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class AgentCapability(str, Enum):
    """Agent 能力标签，用于搜索和推荐。"""

    CHAT = "chat"
    TASK_EXECUTION = "task_execution"
    DATA_ANALYSIS = "data_analysis"
    CODE_GENERATION = "code_generation"
    KNOWLEDGE_BASE = "knowledge_base"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    CUSTOM = "custom"


class AgentRegistration(BaseModel):
    """Agent 注册请求。

    Agent 在 NexusMatrix 注册时需要提供自己的基本信息，
    系统会同时创建 Matrix 用户并分配 API Key。
    """

    agent_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Agent display name",
    )
    description: str = Field(
        ..., min_length=10, max_length=2000,
        description="Detailed description of the agent's purpose and capabilities",
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="List of capability tags for search/discovery",
    )
    metadata: Optional[Dict[str, str]] = Field(
        None, description="Additional metadata (key-value pairs)",
    )
    webhook_url: Optional[str] = Field(
        None, description="Webhook URL for receiving event notifications",
    )
    owner: Optional[str] = Field(
        None, max_length=100,
        description="Owner identifier (person or organization)",
    )
    preferred_username: Optional[str] = Field(
        None, max_length=50,
        description="Preferred Matrix username (e.g. agent_id). If provided, used instead of auto-generated name.",
    )


class AgentProfile(BaseModel):
    """Agent 完整档案。"""

    agent_id: str = Field(..., description="Unique agent identifier")
    agent_name: str = Field(..., description="Agent display name")
    matrix_user_id: str = Field(..., description="Associated Matrix user ID")
    description: str = Field(..., description="Agent description")
    capabilities: List[str] = Field(default_factory=list, description="Capability tags")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata")
    webhook_url: Optional[str] = Field(None, description="Webhook callback URL")
    owner: Optional[str] = Field(None, description="Owner identifier")
    status: AgentStatus = Field(AgentStatus.ACTIVE, description="Current status")
    created_at: datetime = Field(..., description="Registration time")
    updated_at: datetime = Field(..., description="Last update time")
    room_count: int = Field(0, description="Number of rooms joined")


class AgentSearchRequest(BaseModel):
    """Agent 语义搜索请求。

    query 为空字符串时自动转换为通配符 '*'，表示列出所有 Agent。
    """

    query: str = Field(
        ..., max_length=500,
        description="Natural language search query (use '*' or empty string to list all)",
    )
    capabilities: Optional[List[str]] = Field(
        None, description="Filter by capabilities",
    )
    limit: int = Field(10, ge=1, le=100, description="Max results to return")
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="Minimum similarity score")

    @model_validator(mode="before")
    @classmethod
    def _normalize_query(cls, values: dict) -> dict:
        """将空查询字符串转换为通配符 '*'。

        Agent 经常发送 query="" 来列出所有 Agent，
        将其统一转换为 '*' 以触发 list_all 逻辑。
        """
        if isinstance(values, dict):
            query = values.get("query", "")
            if isinstance(query, str) and query.strip() == "":
                values["query"] = "*"
        return values


class AgentSearchResult(BaseModel):
    """搜索结果条目。"""

    agent: AgentProfile = Field(..., description="Matched agent profile")
    score: float = Field(..., description="Similarity score (0-1)")
    highlights: Optional[List[str]] = Field(
        None, description="Matched text highlights"
    )
