"""
@file_name: embedding.py
@author: Bin Liang
@date: 2026-03-03
@description: 嵌入向量工具

通过 OpenAI Embedding API 生成文本嵌入向量，
支持语义搜索中的相似度计算。采用延迟初始化策略。
"""

import os
from typing import List

import numpy as np
from loguru import logger


class EmbeddingService:
    """嵌入向量服务。

    使用 OpenAI Embedding API 生成文本向量，
    提供编码、批量编码和余弦相似度计算功能。
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> None:
        """初始化嵌入服务。

        Args:
            model: OpenAI 嵌入模型名称。
            api_key: OpenAI API Key，为空时从环境变量 OPENAI_API_KEY 读取。
        """
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
            logger.info(f"OpenAI Embedding 客户端已初始化，模型: {self._model}")
        return self._client

    def encode(self, text: str) -> np.ndarray:
        """将文本编码为嵌入向量。

        Args:
            text: 输入文本。

        Returns:
            归一化后的嵌入向量 (float32 ndarray)。
        """
        client = self._get_client()
        resp = client.embeddings.create(input=text, model=self._model)
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        # 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码文本。

        Args:
            texts: 输入文本列表。

        Returns:
            嵌入矩阵，shape = (len(texts), embedding_dim)。
        """
        client = self._get_client()
        resp = client.embeddings.create(input=texts, model=self._model)
        # 按 index 排序确保顺序一致
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        vecs = np.array([d.embedding for d in sorted_data], dtype=np.float32)
        # 逐行归一化
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        return vecs / norms

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度。

        由于向量已归一化，余弦相似度等于点积。

        Args:
            a: 向量 a。
            b: 向量 b。

        Returns:
            相似度分数 (0-1)。
        """
        return float(np.dot(a, b))

    @staticmethod
    def batch_cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """计算查询向量与矩阵中所有向量的余弦相似度。

        Args:
            query: 查询向量，shape = (dim,)。
            matrix: 候选矩阵，shape = (n, dim)。

        Returns:
            相似度数组，shape = (n,)。
        """
        return np.dot(matrix, query)

    def to_bytes(self, embedding: np.ndarray) -> bytes:
        """将 embedding 转为字节串（用于数据库存储）。"""
        return embedding.tobytes()

    def from_bytes(self, data: bytes) -> np.ndarray:
        """从字节串恢复 embedding。"""
        return np.frombuffer(data, dtype=np.float32)
