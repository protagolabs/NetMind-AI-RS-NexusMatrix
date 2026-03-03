"""
@file_name: sync.py
@author: Bin Liang
@date: 2026-03-03
@description: 同步 API 端点

提供 Matrix 事件同步功能，支持长轮询和增量同步。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from nio import AsyncClient

from nexus_matrix.api.deps import get_matrix_client, get_sync_service
from nexus_matrix.core.sync_service import SyncService
from nexus_matrix.models.common import ApiResponse
from nexus_matrix.models.sync import SyncResponse

router = APIRouter(prefix="/sync", tags=["Sync"])


@router.get(
    "",
    response_model=ApiResponse[SyncResponse],
    summary="Sync events from Matrix server",
    description="Long-poll for new events. Pass 'since' token for incremental sync. "
    "First call without 'since' performs initial sync.",
)
async def sync_events(
    since: Optional[str] = Query(None, description="Pagination token from previous sync"),
    timeout: int = Query(30000, ge=0, le=60000, description="Long-poll timeout in ms"),
    client: AsyncClient = Depends(get_matrix_client),
    sync_service: SyncService = Depends(get_sync_service),
):
    """同步 Matrix 事件。

    使用长轮询机制获取新事件：
    - 首次调用不传 since，执行全量同步
    - 后续调用传入上次返回的 next_batch，实现增量同步
    """
    try:
        result = await sync_service.sync(client, timeout=timeout, since=since)
        return ApiResponse.ok(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
