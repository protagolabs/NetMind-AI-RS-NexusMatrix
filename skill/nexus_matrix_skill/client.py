"""
@file_name: client.py
@author: Bin Liang
@date: 2026-03-03
@description: HTTP 客户端

封装与 NexusMatrix 服务的 HTTP 通信，
处理认证、重试、错误处理等底层细节。
"""

import json
import logging
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin

logger = logging.getLogger("nexus_matrix_skill")


class NexusMatrixClient:
    """NexusMatrix HTTP 客户端。

    使用 urllib（标准库）实现 HTTP 通信，
    零外部依赖，确保 Skill 包轻量可移植。
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        """初始化 HTTP 客户端。

        Args:
            base_url: NexusMatrix 服务地址。
            api_key: API Key（注册后获得）。
            timeout: 请求超时（秒）。
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = value

    def _build_url(self, path: str) -> str:
        """构造完整 URL。"""
        return f"{self._base_url}{path}"

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """构造请求头。"""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求。

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE)。
            path: API 路径 (e.g., /api/v1/auth/register)。
            data: 请求体（JSON）。
            params: 查询参数。

        Returns:
            响应 JSON 字典。

        Raises:
            RuntimeError: 请求失败。
        """
        url = self._build_url(path)

        # 添加查询参数
        if params:
            query_parts = []
            for k, v in params.items():
                if v is not None:
                    query_parts.append(f"{k}={v}")
            if query_parts:
                url += "?" + "&".join(query_parts)

        body = json.dumps(data).encode("utf-8") if data else None
        headers = self._build_headers()

        req = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(req, timeout=self._timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                return response_data
        except HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                error_data = json.loads(error_body)
                error_msg = error_data.get("detail", error_body)
            except (json.JSONDecodeError, KeyError):
                error_msg = error_body
            logger.error(f"HTTP {e.code} {method} {path}: {error_msg}")
            raise RuntimeError(f"API error ({e.code}): {error_msg}")
        except URLError as e:
            logger.error(f"Connection error {method} {path}: {e}")
            raise RuntimeError(f"Connection error: {e}")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET 请求。"""
        return self.request("GET", path, params=params)

    def post(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST 请求。"""
        return self.request("POST", path, data=data)

    def put(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """PUT 请求。"""
        return self.request("PUT", path, data=data)

    def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """DELETE 请求。"""
        return self.request("DELETE", path, params=params)
