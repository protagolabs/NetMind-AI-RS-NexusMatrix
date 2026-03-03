"""
@file_name: common.py
@author: Bin Liang
@date: 2026-03-03
@description: 通用数据模型

定义 API 响应包装、分页、错误详情等跨模块共用的数据结构。
"""

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """错误详情。"""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应包装。

    所有 API 端点都返回此格式，确保响应结构一致。
    """

    success: bool = Field(..., description="Whether the request succeeded")
    data: Optional[T] = Field(None, description="Response payload")
    error: Optional[ErrorDetail] = Field(None, description="Error details if failed")

    @classmethod
    def ok(cls, data: Any = None) -> "ApiResponse":
        """构造成功响应。"""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse":
        """构造失败响应。"""
        return cls(success=False, error=ErrorDetail(code=code, message=message))


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应。"""

    items: List[T] = Field(default_factory=list, description="Result items")
    total: int = Field(0, description="Total count")
    offset: int = Field(0, description="Current offset")
    limit: int = Field(20, description="Page size")
    has_more: bool = Field(False, description="Whether more items exist")
