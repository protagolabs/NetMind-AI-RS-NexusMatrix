"""
@file_name: search_service.py
@author: Bin Liang
@date: 2026-03-03
@description: Agent 语义搜索服务

基于 sentence-transformers 嵌入向量实现的语义搜索，
支持对注册 Agent 按自然语言描述进行相似度匹配和排序。
"""

from typing import List, Optional

import numpy as np
from loguru import logger

from nexus_matrix.models.registry import (
    AgentProfile,
    AgentSearchRequest,
    AgentSearchResult,
)
from nexus_matrix.storage.repositories.agent_repo import AgentRepository
from nexus_matrix.utils.embedding import EmbeddingService


class SearchService:
    """Agent 语义搜索服务。

    工作流程：
    1. 将搜索查询编码为 embedding 向量
    2. 与所有 Agent 的 embedding 计算余弦相似度
    3. 按能力标签过滤
    4. 按相似度降序排序返回结果
    """

    def __init__(
        self,
        agent_repo: AgentRepository,
        embedding_service: EmbeddingService,
    ) -> None:
        self._agent_repo = agent_repo
        self._embedding_service = embedding_service

    async def search(self, request: AgentSearchRequest) -> List[AgentSearchResult]:
        """执行语义搜索。

        Args:
            request: 搜索请求（包含查询文本、过滤条件、结果限制）。

        Returns:
            按相似度降序排列的搜索结果列表。
        """
        # 通配符 '*' 表示列出所有 Agent
        if request.query.strip() == "*":
            return await self._list_all(request)

        try:
            # 编码查询文本
            query_embedding = self._embedding_service.encode(request.query)
        except Exception as e:
            logger.warning(f"编码查询失败，回退到关键词搜索: {e}")
            return await self._fallback_keyword_search(request)

        # 获取所有有 embedding 的 Agent
        agents_with_embeddings = await self._agent_repo.get_all_with_embeddings()
        if not agents_with_embeddings:
            return []

        # 分离数据
        profiles = [item[0] for item in agents_with_embeddings]
        embeddings = np.array([item[1] for item in agents_with_embeddings])

        # 计算余弦相似度
        scores = EmbeddingService.batch_cosine_similarity(query_embedding, embeddings)

        # 组装结果并过滤
        results = []
        for profile, score in zip(profiles, scores):
            # 分数过滤
            if score < request.min_score:
                continue

            # 能力标签过滤
            if request.capabilities:
                if not any(
                    cap in profile.capabilities for cap in request.capabilities
                ):
                    continue

            results.append(AgentSearchResult(
                agent=profile,
                score=float(score),
            ))

        # 按分数降序排序
        results.sort(key=lambda x: x.score, reverse=True)

        # 限制结果数
        return results[: request.limit]

    async def _list_all(self, request: AgentSearchRequest) -> List[AgentSearchResult]:
        """列出所有活跃 Agent（通配符搜索）。

        Args:
            request: 搜索请求（用于 capabilities 过滤和 limit 限制）。

        Returns:
            所有匹配的 Agent，score 固定为 1.0。
        """
        all_agents = await self._agent_repo.list_active(limit=request.limit)
        results = []
        for agent in all_agents:
            if request.capabilities:
                if not any(cap in agent.capabilities for cap in request.capabilities):
                    continue
            results.append(AgentSearchResult(agent=agent, score=1.0))
        return results

    async def _fallback_keyword_search(
        self, request: AgentSearchRequest
    ) -> List[AgentSearchResult]:
        """关键词回退搜索。

        当 embedding 服务不可用时，使用简单的关键词匹配。

        Args:
            request: 搜索请求。

        Returns:
            搜索结果列表。
        """
        all_agents = await self._agent_repo.list_active(limit=500)
        query_lower = request.query.lower()
        query_terms = query_lower.split()

        results = []
        for agent in all_agents:
            # 计算关键词匹配分数
            text = f"{agent.agent_name} {agent.description} {' '.join(agent.capabilities)}".lower()
            matched = sum(1 for term in query_terms if term in text)
            if matched == 0:
                continue
            score = matched / len(query_terms)

            if score < request.min_score:
                continue

            # 能力过滤
            if request.capabilities:
                if not any(cap in agent.capabilities for cap in request.capabilities):
                    continue

            results.append(AgentSearchResult(agent=agent, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[: request.limit]

    async def recommend_similar(
        self, agent_id: str, limit: int = 5
    ) -> List[AgentSearchResult]:
        """推荐相似 Agent。

        基于给定 Agent 的 embedding 查找最相似的其他 Agent。

        Args:
            agent_id: 参照 Agent ID。
            limit: 最大推荐数。

        Returns:
            相似 Agent 列表。
        """
        # 获取目标 Agent 的 embedding
        target = await self._agent_repo.get_by_id(agent_id)
        if not target:
            return []

        agents_with_embeddings = await self._agent_repo.get_all_with_embeddings()
        if not agents_with_embeddings:
            return []

        # 找到目标 Agent 的 embedding
        target_embedding = None
        for profile, emb in agents_with_embeddings:
            if profile.agent_id == agent_id:
                target_embedding = emb
                break

        if target_embedding is None:
            return []

        # 计算相似度（排除自身）
        results = []
        for profile, emb in agents_with_embeddings:
            if profile.agent_id == agent_id:
                continue
            score = float(EmbeddingService.cosine_similarity(target_embedding, emb))
            if score > 0.3:
                results.append(AgentSearchResult(agent=profile, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
