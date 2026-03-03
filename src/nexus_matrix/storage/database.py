"""
@file_name: database.py
@author: Bin Liang
@date: 2026-03-03
@description: 异步 SQLite 数据库客户端

基于 aiosqlite 封装的异步数据库客户端，负责：
- 连接管理（单例模式）
- 表创建与迁移
- 提供便捷的 CRUD 方法
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from loguru import logger


class Database:
    """异步 SQLite 数据库客户端。

    使用 aiosqlite 实现异步数据库操作，
    内部维护一个连接，支持 WAL 模式以提升并发性能。
    """

    def __init__(self, db_path: str) -> None:
        """初始化数据库客户端。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """建立数据库连接并初始化表结构。"""
        # 确保数据库目录存在
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self._db_path)
        # 启用 WAL 模式，提升并发读写性能
        await self._conn.execute("PRAGMA journal_mode=WAL")
        # 启用外键约束
        await self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = aiosqlite.Row

        await self._create_tables()
        logger.info(f"数据库已连接: {self._db_path}")

    async def disconnect(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    async def _create_tables(self) -> None:
        """创建所有表结构。

        采用 IF NOT EXISTS 保证幂等性。
        """
        await self._conn.executescript("""
            -- Agent 注册表：存储所有注册 Agent 的信息
            CREATE TABLE IF NOT EXISTS agents (
                agent_id        TEXT PRIMARY KEY,
                agent_name      TEXT NOT NULL,
                matrix_user_id  TEXT NOT NULL UNIQUE,
                description     TEXT NOT NULL DEFAULT '',
                capabilities    TEXT NOT NULL DEFAULT '[]',
                metadata        TEXT DEFAULT '{}',
                webhook_url     TEXT,
                owner           TEXT,
                status          TEXT NOT NULL DEFAULT 'active',
                embedding       BLOB,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            -- Agent 搜索索引
            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(agent_name);

            -- API Key 表：管理 Agent 的访问凭据
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id          TEXT PRIMARY KEY,
                api_key_hash    TEXT NOT NULL UNIQUE,
                agent_id        TEXT NOT NULL,
                matrix_user_id  TEXT NOT NULL,
                access_token    TEXT NOT NULL,
                device_id       TEXT NOT NULL DEFAULT '',
                is_admin        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at      TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(api_key_hash);
            CREATE INDEX IF NOT EXISTS idx_api_keys_agent ON api_keys(agent_id);

            -- 同步状态表：记录每个 Agent 的同步进度
            CREATE TABLE IF NOT EXISTS sync_tokens (
                user_id         TEXT PRIMARY KEY,
                next_batch      TEXT NOT NULL DEFAULT '',
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        await self._conn.commit()

    # ── 通用 CRUD 方法 ──

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """执行 SQL 语句。"""
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """查询单条记录。"""
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """查询多条记录。"""
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def insert(self, table: str, data: Dict[str, Any]) -> None:
        """插入单条记录。

        Args:
            table: 表名。
            data: 字段名到值的映射。
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = tuple(
            json.dumps(v) if isinstance(v, (dict, list)) else v
            for v in data.values()
        )
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        await self._conn.execute(sql, values)
        await self._conn.commit()

    async def update(
        self, table: str, filters: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """更新记录。

        Args:
            table: 表名。
            filters: WHERE 条件。
            data: 要更新的字段。

        Returns:
            受影响的行数。
        """
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        where_clause = " AND ".join(f"{k} = ?" for k in filters.keys())
        values = tuple(
            json.dumps(v) if isinstance(v, (dict, list)) else v
            for v in list(data.values()) + list(filters.values())
        )
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        cursor = await self._conn.execute(sql, values)
        await self._conn.commit()
        return cursor.rowcount

    async def delete(self, table: str, filters: Dict[str, Any]) -> int:
        """删除记录。

        Args:
            table: 表名。
            filters: WHERE 条件。

        Returns:
            受影响的行数。
        """
        where_clause = " AND ".join(f"{k} = ?" for k in filters.keys())
        values = tuple(filters.values())
        sql = f"DELETE FROM {table} WHERE {where_clause}"
        cursor = await self._conn.execute(sql, values)
        await self._conn.commit()
        return cursor.rowcount
