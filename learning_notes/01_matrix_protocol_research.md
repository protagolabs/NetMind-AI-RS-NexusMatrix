# Matrix 协议研究笔记

> 研究日期: 2026-03-03
> 目的: 为 NexusMatrix 项目提供 Matrix 协议的完整技术参考

---

## 一、Matrix 协议概述

### 1.1 什么是 Matrix

Matrix 是一套**开放的去中心化通信协议**，定义了一组用于去中心化通信的开放 API。它适用于：
- 即时通讯 (IM)
- VoIP 信令
- IoT 通信
- 桥接现有通信孤岛

**核心理念**：通过全球开放的联邦服务器网络，安全地发布、持久化和订阅数据，没有单一控制点。

### 1.2 架构模型

```
┌──────────┐     HTTP      ┌──────────────┐     Federation     ┌──────────────┐     HTTP      ┌──────────┐
│ Client A │ ◄──────────► │ Homeserver A │ ◄───────────────► │ Homeserver B │ ◄──────────► │ Client B │
└──────────┘  Client-Server └──────────────┘   Server-Server   └──────────────┘  Client-Server └──────────┘
                  API                              API                                API
```

- **Client**: 用户端应用（Element、FluffyChat 等）
- **Homeserver**: 存储用户数据和房间历史的服务器
- **Federation**: Homeserver 之间的数据同步机制

### 1.3 联邦 (Federation)

- Homeserver 将通信历史建模为**偏序事件图**（event graph）
- 使用 Server-Server API 在参与的服务器之间以**最终一致性**同步
- 联邦流量使用 HTTPS 加密，并使用每个服务器的私钥签名以防止欺骗
- 截至 2025 年 12 月，已发现 11,861 个可联邦的 Matrix 服务器

---

## 二、核心概念

### 2.1 房间 (Rooms)

房间是 Matrix 中的核心通信容器：
- 每个房间有一个**唯一技术标识符** (Room ID)：`!RtZiWTovChPysCUIgn:matrix.example.com`
- 可以有零个或多个**人类可读别名** (Alias)：`#goodfriends:example.com`
- 房间数据在所有参与用户的 Homeserver 之间复制
- 没有单个 Homeserver 拥有房间的控制权

**房间类型**：
- **普通房间**: 标准聊天室
- **直接消息 (DM)**: 初始只有两个成员且 `is_direct` 设为 `true`
- **Space**: 房间的组织容器，可以包含其他房间和 Space（类似文件夹）
- **加密房间**: 通过 `m.room.encryption` 状态事件标记

### 2.2 事件 (Events)

事件是特定的 JSON 对象，描述用户试图做什么。

**事件 JSON 结构**：
```json
{
  "origin_server_ts": 1526072700313,
  "sender": "@Alice:matrix.alice.tld",
  "event_id": "$1526072700393WQoZb:matrix.alice.tld",
  "unsigned": {
    "age": 97,
    "transaction_id": "m1526072700255.17"
  },
  "content": {
    "body": "Hello Bob!",
    "msgtype": "m.text"
  },
  "type": "m.room.message",
  "room_id": "!TCnDZIwFBeQyBCciFD:matrix.alice.tld"
}
```

**三种事件类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| **状态事件 (State Events)** | 包含 `state_key` 属性，描述房间的持久状态 | `m.room.create`, `m.room.name`, `m.room.topic`, `m.room.member`, `m.room.join_rules`, `m.room.power_levels`, `m.room.encryption` |
| **时间线事件 (Timeline/Message Events)** | 构成房间时间线，描述瞬时活动 | `m.room.message`, `m.room.redaction` |
| **临时事件 (Ephemeral Events)** | 不包含在房间时间线中，传播不持久的信息 | 输入通知 (typing notifications) |

**状态事件示例**：
```json
{
  "content": {
    "join_rule": "public"
  },
  "event_id": "$1526078716401exXBQ:matrix.project.tld",
  "origin_server_ts": 1526078716874,
  "room_id": "!RtZiWTovChPysCUIgn:matrix.project.tld",
  "sender": "@Alice:matrix.project.tld",
  "state_key": "",
  "type": "m.room.join_rules"
}
```

### 2.3 权力等级 (Power Levels)

- 房间创建者默认获得 power level **100**
- 新加入成员默认为 **0**
- 发送消息通常需要 **0**
- 删除他人消息通常需要 **50**
- 所有房间内操作都需要最低 power level

### 2.4 房间成员状态

成员状态通过 `m.room.member` 状态事件管理：
- `invite` - 已邀请
- `join` - 已加入
- `leave` - 已离开
- `ban` - 已封禁
- `knock` - 请求加入（敲门）

### 2.5 同步 (Sync)

Matrix 使用**长轮询** (Long-polling) 机制接收事件：
1. 客户端向 `/sync` 端点发起请求
2. 服务器等待直到超时（通常 30 秒）或有新事件
3. 响应包含 `next_batch` 令牌
4. 客户端在下一次请求中传递 `next_batch` 以获取增量更新

**Sync 响应结构**：
```json
{
  "next_batch": "s72595_4483_1934",
  "rooms": {
    "join": {
      "!room_id:server": {
        "state": { "events": [...] },
        "timeline": { "events": [...] },
        "ephemeral": { "events": [...] }
      }
    },
    "invite": { ... },
    "leave": { ... }
  },
  "presence": { ... }
}
```

### 2.6 端到端加密 (E2EE)

- 使用 **Olm** 协议（1对1）和 **Megolm** 协议（群组）
- 通过 `m.room.encryption` 状态事件启用
- 默认对直接消息和群组消息启用
- 需要密钥交换和设备验证

### 2.7 房间版本 (Room Versions)

- 房间有严格的内容规则和算法（冲突解决、事件接受等）
- 通过房间版本管理不同的规则集和期望
- 允许通过新版本改进房间行为

---

## 三、Client-Server API（REST 端点详解）

### 3.1 认证端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/_matrix/client/v3/login` | 获取服务器支持的登录方式 |
| POST | `/_matrix/client/v3/login` | 提交凭证获取 access_token |
| POST | `/_matrix/client/v3/register` | 注册新用户账户 |
| POST | `/_matrix/client/v3/logout` | 使当前 access_token 失效 |
| POST | `/_matrix/client/v3/logout/all` | 登出所有设备 |
| POST | `/_matrix/client/v3/refresh` | 使用 refresh_token 获取新 access_token |
| GET | `/_matrix/client/v3/account/whoami` | 返回当前认证用户的 user_id |

**认证流程**：
```
1. POST /register → 服务器返回需要的认证阶段
2. POST /register (带 auth 字段) → 完成认证
3. 返回 access_token, device_id, user_id
4. 后续请求通过 Authorization: Bearer <token> 认证
```

**注册请求示例**：
```json
{
  "auth": {
    "type": "m.login.dummy",
    "session": "HrvSksPaKpglatvIqJHVEfkd"
  },
  "username": "Alice",
  "password": "1L0v3M4tr!x"
}
```

**注册成功响应**：
```json
{
  "access_token": "olic0yeVa1pore2Kie4Wohsh",
  "device_id": "FOZLAWNKLD",
  "home_server": "matrix.project.tld",
  "user_id": "@Alice:matrix.project.tld"
}
```

### 3.2 房间端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/_matrix/client/v3/createRoom` | 创建新房间 |
| POST | `/_matrix/client/v3/join/{roomIdOrAlias}` | 通过 ID 或别名加入房间 |
| POST | `/_matrix/client/v3/rooms/{roomId}/leave` | 离开房间 |
| POST | `/_matrix/client/v3/rooms/{roomId}/invite` | 邀请用户加入房间 |
| POST | `/_matrix/client/v3/rooms/{roomId}/kick` | 踢出用户 |
| POST | `/_matrix/client/v3/rooms/{roomId}/ban` | 封禁用户 |

**创建房间请求示例**：
```bash
curl -X POST "https://server/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Room",
    "topic": "A test room",
    "visibility": "private",
    "preset": "private_chat",
    "invite": ["@bob:server"],
    "is_direct": false
  }'
```

### 3.3 消息端点

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/_matrix/client/v3/rooms/{roomId}/send/{eventType}/{txnId}` | 发送时间线事件（消息） |
| GET | `/_matrix/client/v3/rooms/{roomId}/messages` | 获取房间消息历史 |
| PUT | `/_matrix/client/v3/rooms/{roomId}/redact/{eventId}/{txnId}` | 删除/隐藏已发送的消息 |

**发送消息示例**：
```bash
curl -X PUT "https://server/_matrix/client/v3/rooms/!roomId:server/send/m.room.message/txn001" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"body": "Hello!", "msgtype": "m.text"}'
```

**txnId**：事务 ID，用于唯一标识请求，防止重复发送。

### 3.4 状态端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/_matrix/client/v3/rooms/{roomId}/state` | 获取房间所有状态事件 |
| GET | `/_matrix/client/v3/rooms/{roomId}/state/{eventType}/{stateKey}` | 获取特定状态事件 |
| PUT | `/_matrix/client/v3/rooms/{roomId}/state/{eventType}/{stateKey}` | 设置/更新房间状态事件 |

### 3.5 同步端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/_matrix/client/v3/sync` | 同步对话历史和房间状态 |

**Sync 参数**：
- `since`: 上一次 sync 返回的 `next_batch`
- `timeout`: 长轮询超时时间（毫秒），通常 30000
- `filter`: 过滤器（可选）

### 3.6 用户/资料端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/_matrix/client/v3/profile/{userId}` | 获取用户完整资料 |
| PUT | `/_matrix/client/v3/profile/{userId}/displayname` | 更新显示名称 |
| PUT | `/_matrix/client/v3/profile/{userId}/avatar_url` | 更新头像 |

---

## 四、Python 库对比

### 4.1 matrix-nio（推荐）

**定位**：基于 sans I/O 原则的异步 Matrix 客户端库。

**安装**：
```bash
# 基础安装（无加密）
pip install matrix-nio

# 带 E2EE 支持
apt-get install libolm-dev  # 先安装系统依赖
pip install matrix-nio[e2e]
```

**核心特性**：
- 透明的端到端加密 (E2EE)
- 加密文件上传/下载
- Space 支持
- 手动和 emoji 验证
- 自定义认证类型
- 线程支持
- Typing 通知、消息删除、已读回执
- 反应 (m.reaction) 和标签 (m.tag)

**尚未实现**：
- 交叉签名
- 服务端密钥备份

**核心类和方法**：

```python
from nio import AsyncClient, MatrixRoom, RoomMessageText

# --- 认证 ---
client = AsyncClient("https://homeserver", "@user:server")
await client.login("password")
await client.logout()
await client.register("username", "password")  # 注册
await client.whoami()  # 获取当前用户身份

# --- 房间管理 ---
await client.room_create(
    visibility=RoomVisibility.private,
    name="Room Name",
    topic="Room Topic",
    invite=["@user:server"],
    is_direct=True,          # 标记为直接消息
    preset=RoomPreset.private_chat,
    initial_state=[...],     # 初始状态事件
    power_level_override={...}
)
await client.join("!roomId:server")           # 加入房间
await client.room_leave("!roomId:server")     # 离开房间
await client.room_invite("!roomId:server", "@user:server")  # 邀请
await client.room_kick("!roomId:server", "@user:server")    # 踢出
await client.room_ban("!roomId:server", "@user:server")     # 封禁
await client.room_unban("!roomId:server", "@user:server")   # 解封
await client.room_forget("!roomId:server")    # 遗忘房间

# --- 消息 ---
await client.room_send(
    room_id="!roomId:server",
    message_type="m.room.message",
    content={"msgtype": "m.text", "body": "Hello!"}
)
await client.room_redact("!roomId:server", "event_id", reason="spam")
await client.room_typing("!roomId:server", typing_state=True)
await client.room_read_markers("!roomId:server", fully_read_event="$eventId")

# --- 同步 ---
await client.sync(timeout=30000)                # 单次同步
await client.sync_forever(timeout=30000)         # 持续同步
await client.room_messages("!roomId:server", start="token", limit=10)

# --- 用户/资料 ---
await client.profile_get("@user:server")
await client.profile_set_displayname("New Name")
await client.profile_set_avatar("mxc://...")
await client.set_presence("online")

# --- 加密 ---
await client.keys_upload()
await client.keys_query()
await client.keys_claim({"@user:server": {"device_id": "signed_curve25519"}})
```

**事件回调模式**：
```python
async def message_callback(room: MatrixRoom, event: RoomMessageText) -> None:
    print(f"{room.display_name} | {room.user_name(event.sender)}: {event.body}")

client.add_event_callback(message_callback, RoomMessageText)
# 支持多种事件类型的回调
client.add_event_callback(media_callback, (RoomMessageMedia, RoomEncryptedMedia))

# 响应回调
client.add_response_callback(sync_cb, SyncResponse)

await client.sync_forever(timeout=30000)
```

**完整 Bot 示例**：
```python
import asyncio
from nio import AsyncClient, MatrixRoom, RoomMessageText

async def message_callback(room: MatrixRoom, event: RoomMessageText) -> None:
    print(f"Message received in room {room.display_name}")
    print(f"{room.user_name(event.sender)} | {event.body}")

async def main() -> None:
    client = AsyncClient("https://matrix.example.org", "@alice:example.org")
    client.add_event_callback(message_callback, RoomMessageText)

    print(await client.login("my-secret-password"))
    # 发送消息
    await client.room_send(
        room_id="!my-fave-room:example.org",
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": "Hello world!"},
    )
    # 持续监听
    await client.sync_forever(timeout=30000)

asyncio.run(main())
```

### 4.2 其他 Python 库

| 库 | 定位 | 适用场景 |
|---|---|---|
| **matrix-nio** | 底层异步客户端库 | 需要完全控制的服务/Agent |
| **simplematrixbotlib** | 基于 matrix-nio 的高层封装 | 快速构建简单 bot |
| **maubot** | 插件式 bot 系统 | 可扩展的 bot 平台 |
| **python-matrix-bot-api** | 简单 bot API | 已较旧，不推荐 |

**对于 NexusMatrix 项目的选择建议**：
- 使用 **matrix-nio** 作为底层库，因为我们需要完全控制 Matrix 交互
- 不使用 simplematrixbotlib 或 maubot，因为它们的抽象层会限制我们的灵活性

---

## 五、Homeserver 部署方案

### 5.1 方案对比

| 特性 | Synapse | Dendrite | Conduit |
|------|---------|----------|---------|
| 语言 | Python/Twisted | Go | Rust |
| 成熟度 | 最成熟（85.5% 市场份额） | 维护模式 | 发展中 |
| 资源占用 | 较高 | 低 | 最低 |
| 扩展性 | 单实例→Workers→多实例 | 单体→微服务 | 仅单实例 |
| 数据库 | PostgreSQL/SQLite | PostgreSQL | SQLite/RocksDB |
| 推荐场景 | 生产环境 | 轻量生产 | 个人/实验 |

### 5.2 Synapse Docker 部署（推荐）

**生成配置**：
```bash
docker run -it --rm \
  -v synapse-data:/data \
  -e SYNAPSE_SERVER_NAME=matrix.example.com \
  -e SYNAPSE_REPORT_STATS=no \
  matrixdotorg/synapse:latest generate
```

**docker-compose.yml**：
```yaml
version: "3.3"
services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    environment:
      - SYNAPSE_CONFIG_PATH=/data/homeserver.yaml
    volumes:
      - synapse-data:/data
    ports:
      - "8008:8008"
    depends_on:
      - postgres

  postgres:
    image: postgres:15
    container_name: synapse-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: synapse
      POSTGRES_USER: synapse
      POSTGRES_PASSWORD: synapse_password
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --lc-collate=C --lc-ctype=C"
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  synapse-data:
  postgres-data:
```

**关键 homeserver.yaml 配置**：
```yaml
server_name: "matrix.example.com"

# 监听端口
listeners:
  - port: 8008
    type: http
    resources:
      - names: [client, federation]

# 数据库配置（使用 PostgreSQL）
database:
  name: psycopg2
  args:
    user: synapse
    password: synapse_password
    database: synapse
    host: postgres
    cp_min: 5
    cp_max: 10

# 注册配置
enable_registration: true
enable_registration_without_verification: true  # 仅开发环境！

# 共享密钥注册（用于编程方式创建用户）
registration_shared_secret: "your-super-secret-key"

# 日志级别
log_config: "/data/matrix.example.com.log.config"
```

### 5.3 编程方式创建用户

**方式一：命令行**：
```bash
docker exec -it synapse register_new_matrix_user \
  http://localhost:8008 \
  -c /data/homeserver.yaml \
  -u bot_user \
  -p bot_password \
  --no-admin
```

**方式二：Admin API**：
```
POST /_synapse/admin/v1/register

# 需要先获取 nonce
GET /_synapse/admin/v1/register

# 然后计算 MAC (HMAC-SHA1) 并提交
POST /_synapse/admin/v1/register
{
  "nonce": "...",
  "username": "bot_user",
  "password": "bot_password",
  "admin": false,
  "mac": "hex_digest_of_hmac_sha1"
}
```

### 5.4 Synapse Admin API

管理端点前缀：`/_synapse/admin/`，需要管理员 access_token。

**用户管理**：
- `GET /_synapse/admin/v2/users` - 列出所有用户
- `GET /_synapse/admin/v2/users/{userId}` - 查询用户详情
- `PUT /_synapse/admin/v2/users/{userId}` - 创建/修改用户
- `POST /_synapse/admin/v1/deactivate/{userId}` - 停用用户
- `POST /_synapse/admin/v1/reset_password/{userId}` - 重置密码

**房间管理**：
- `GET /_synapse/admin/v1/rooms` - 列出所有房间
- `GET /_synapse/admin/v1/rooms/{roomId}` - 查询房间详情
- `DELETE /_synapse/admin/v2/rooms/{roomId}` - 删除房间
- `GET /_synapse/admin/v1/rooms/{roomId}/members` - 获取房间成员
- `GET /_synapse/admin/v1/rooms/{roomId}/state` - 获取房间状态

---

## 六、Bot/Agent 开发最佳实践

### 6.1 架构建议

1. **使用 matrix-nio 的 AsyncClient** 作为底层通信层
2. **将 Matrix 交互封装为 Service 层**，隐藏协议细节
3. **使用回调模式** 处理入站事件
4. **持久化 access_token**，避免每次重新登录
5. **使用 `sync_forever`** 进行持续监听，在单独的 asyncio task 中运行

### 6.2 关键模式

**Token 持久化**：
```python
# 首次登录后保存凭证
credentials = {
    "homeserver": "https://matrix.example.org",
    "user_id": response.user_id,
    "device_id": response.device_id,
    "access_token": response.access_token,
}
# 保存到文件或数据库

# 后续启动直接恢复
client = AsyncClient(credentials["homeserver"])
client.restore_login(
    user_id=credentials["user_id"],
    device_id=credentials["device_id"],
    access_token=credentials["access_token"],
)
```

**后台 Sync 循环**：
```python
# 在后台任务中运行 sync_forever
sync_task = asyncio.create_task(client.sync_forever(timeout=30000))

# 主逻辑可以并行发送消息
await client.room_send(...)

# 清理
sync_task.cancel()
await client.close()
```

**事件过滤**：
```python
# 只处理新消息，忽略历史消息
async def message_callback(room, event):
    # 忽略自己发送的消息
    if event.sender == client.user_id:
        return
    # 忽略旧消息（sync 初始化时可能收到历史消息）
    if event.server_timestamp < start_time:
        return
    # 处理新消息
    await handle_message(room, event)
```

### 6.3 对于 NexusMatrix 项目的架构建议

```
┌──────────────────────────────────────────┐
│          NexusMatrix Service             │
├──────────────────────────────────────────┤
│  FastAPI (REST API for Agents)           │  ← Agent 调用的 HTTP API
├──────────────────────────────────────────┤
│  Agent Registry (注册中心)               │  ← 中心化注册 + 语义搜索
├──────────────────────────────────────────┤
│  Matrix Service Layer                    │  ← 封装 Matrix 操作
│  ├── AuthService (认证管理)              │
│  ├── RoomService (房间管理)              │
│  ├── MessageService (消息收发)           │
│  └── SyncService (事件同步)              │
├──────────────────────────────────────────┤
│  matrix-nio AsyncClient                  │  ← 底层 Matrix 客户端
├──────────────────────────────────────────┤
│  Synapse Homeserver (Docker)             │  ← 自部署的 Homeserver
└──────────────────────────────────────────┘
```

---

## 七、重要注意事项

1. **Room ID 需要 URL 编码**：`!` → `%21`，`:` → `%3A`
2. **txnId 必须唯一**：同一 access_token 下的事务 ID 不能重复
3. **Sync 初始化**：首次 sync 会返回大量历史数据，需要设置过滤器
4. **E2EE 复杂性**：端到端加密显著增加复杂度，建议 Agent 场景先不启用
5. **自定义事件类型**：Matrix 支持非 `m.` 命名空间的自定义事件类型和内容
6. **Synapse SQLite vs PostgreSQL**：开发用 SQLite，生产必须用 PostgreSQL

---

## 参考资料

- [Matrix 官方规范](https://spec.matrix.org/latest/)
- [Client-Server API 规范 v1.17](https://spec.matrix.org/v1.17/client-server-api/)
- [matrix-nio GitHub](https://github.com/matrix-nio/matrix-nio)
- [matrix-nio API 文档](https://matrix-nio.readthedocs.io/en/latest/nio.html)
- [matrix-nio 示例](https://matrix-nio.readthedocs.io/en/latest/examples.html)
- [Enter the Matrix 教程](https://brendan.abolivier.bzh/enter-the-matrix/)
- [Matrix 房间与事件概念](https://matrix.org/docs/matrix-concepts/rooms_and_events/)
- [Synapse Docker Hub](https://hub.docker.com/r/matrixdotorg/synapse)
- [Synapse Admin API](https://matrix-org.github.io/synapse/latest/usage/administration/admin_api/)
- [Matrix 服务器对比](https://matrixdocs.github.io/docs/servers/comparison)
- [nio-template (Bot 模板)](https://github.com/anoadragon453/nio-template)
