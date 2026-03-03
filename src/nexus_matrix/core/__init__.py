"""
@file_name: __init__.py
@author: Bin Liang
@date: 2026-03-03
@description: 核心服务层

封装 Matrix 协议操作，提供高层业务逻辑接口。
"""

from nexus_matrix.core.matrix_client_manager import MatrixClientManager
from nexus_matrix.core.auth_service import AuthService
from nexus_matrix.core.room_service import RoomService
from nexus_matrix.core.message_service import MessageService
from nexus_matrix.core.sync_service import SyncService

__all__ = [
    "MatrixClientManager",
    "AuthService",
    "RoomService",
    "MessageService",
    "SyncService",
]
