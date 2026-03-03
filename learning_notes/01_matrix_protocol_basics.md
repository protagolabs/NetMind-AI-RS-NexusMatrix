# Matrix 协议核心知识

## 关键概念

- **Homeserver**: 存储用户数据和房间历史的服务器，每个用户属于一个 homeserver
- **Room**: 所有通信的容器，消息、状态变更都发生在 Room 里
- **Event**: Matrix 中的基本数据单元，分为 State Events（持久状态）和 Timeline Events（时间线消息）
- **Sync**: 客户端通过长轮询 `/sync` 端点获取新事件，使用 `next_batch` token 实现增量同步

## 技术选型

| 组件 | 选择 | 原因 |
|------|------|------|
| Homeserver | Synapse (Docker) | 最成熟、功能最全、Admin API 丰富 |
| Python SDK | matrix-nio | 异步、功能完整、活跃维护 |
| Embedding | OpenAI text-embedding-3-small | 质量高、无本地依赖、API 简单 |
| 数据库 | SQLite (aiosqlite) | 轻量、零配置、适合注册中心 |
| Web 框架 | FastAPI | 异步、高性能、自动文档 |

## Synapse Admin API

关键端点：
- `GET/POST /_synapse/admin/v1/register` - 程序化注册用户（需要 shared_secret）
- `PUT /_synapse/admin/v2/users/{userId}` - 创建/修改用户
- Rate limiting 可以通过 `rc_message` 等配置放宽

## 注意事项

1. 首次同步（无 since token）返回大量历史数据，应过滤旧消息
2. 管理员用户通过 HMAC-SHA1 签名的 shared_secret 方式注册
3. E2EE 增加复杂度（密钥管理），当前先不启用
4. matrix-nio 的 `sync_forever` 内部处理重连，适合后台服务
