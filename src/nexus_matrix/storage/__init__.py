"""
@file_name: __init__.py
@author: Bin Liang
@date: 2026-03-03
@description: 存储层，提供异步数据库访问和 Repository 模式
"""

from nexus_matrix.storage.database import Database

__all__ = ["Database"]
