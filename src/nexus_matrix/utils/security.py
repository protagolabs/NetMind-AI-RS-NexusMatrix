"""
@file_name: security.py
@author: Bin Liang
@date: 2026-03-03
@description: 安全工具

提供 API Key 生成、哈希、验证等安全相关功能。
"""

import hashlib
import secrets
import string


def generate_api_key(prefix: str = "nxm") -> str:
    """生成 API Key。

    格式: {prefix}_{32位随机字符串}
    示例: nxm_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

    Args:
        prefix: Key 前缀，默认 "nxm"（NexusMatrix 缩写）。

    Returns:
        生成的 API Key 明文。
    """
    charset = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(charset) for _ in range(32))
    return f"{prefix}_{random_part}"


def hash_api_key(api_key: str) -> str:
    """对 API Key 做 SHA-256 哈希。

    存储时只保存哈希值，不存储明文，保证安全性。

    Args:
        api_key: API Key 明文。

    Returns:
        SHA-256 哈希值（十六进制字符串）。
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_id(prefix: str, length: int = 8) -> str:
    """生成带前缀的短 ID。

    格式: {prefix}_{length位随机十六进制}
    示例: agt_a1b2c3d4

    Args:
        prefix: ID 前缀。
        length: 随机部分长度。

    Returns:
        生成的 ID。
    """
    random_part = secrets.token_hex(length // 2 + 1)[:length]
    return f"{prefix}_{random_part}"
