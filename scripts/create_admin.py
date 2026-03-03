"""
@file_name: create_admin.py
@author: Bin Liang
@date: 2026-03-03
@description: 管理员用户创建脚本

通过 Synapse Admin API 的 shared_secret 注册接口创建管理员用户。
独立脚本，不依赖项目的其他模块。
"""

import argparse
import hashlib
import hmac
import json
import sys
import urllib.request


def register_user(
    homeserver: str,
    shared_secret: str,
    username: str,
    password: str,
    admin: bool = False,
    display_name: str = "",
) -> dict:
    """通过 Synapse Admin API 注册用户。

    Args:
        homeserver: Synapse 服务器地址。
        shared_secret: 注册共享密钥。
        username: 用户名。
        password: 密码。
        admin: 是否为管理员。
        display_name: 显示名称。

    Returns:
        注册结果字典。
    """
    # Step 1: 获取 nonce
    nonce_url = f"{homeserver}/_synapse/admin/v1/register"
    req = urllib.request.Request(nonce_url)
    with urllib.request.urlopen(req) as resp:
        nonce_data = json.loads(resp.read().decode())
    nonce = nonce_data["nonce"]

    # Step 2: 构造 HMAC
    mac = hmac.new(
        shared_secret.encode("utf-8"),
        digestmod=hashlib.sha1,
    )
    mac.update(nonce.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(username.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(password.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    hex_mac = mac.hexdigest()

    # Step 3: 注册
    payload = {
        "nonce": nonce,
        "username": username,
        "password": password,
        "mac": hex_mac,
        "admin": admin,
    }
    if display_name:
        payload["displayname"] = display_name

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        nonce_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Registration failed ({e.code}): {error_body}", file=sys.stderr)
        # 如果是用户已存在的错误，不算失败
        if "User ID already taken" in error_body:
            print(f"User @{username} already exists, skipping.")
            return {"user_id": f"@{username}:localhost", "existing": True}
        raise


def main():
    parser = argparse.ArgumentParser(description="Create a Matrix user via Synapse Admin API")
    parser.add_argument("--homeserver", default="http://localhost:8008", help="Synapse URL")
    parser.add_argument("--shared-secret", required=True, help="Registration shared secret")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--admin", action="store_true", help="Grant admin privileges")
    parser.add_argument("--display-name", default="", help="Display name")
    args = parser.parse_args()

    result = register_user(
        homeserver=args.homeserver,
        shared_secret=args.shared_secret,
        username=args.username,
        password=args.password,
        admin=args.admin,
        display_name=args.display_name,
    )
    print(f"  User registered: {result.get('user_id', 'unknown')}")


if __name__ == "__main__":
    main()
