#!/usr/bin/env bash
# ============================================================================
# NexusMatrix Auto-Patrol Script
#
# 定时启动无界面 Claude Code，自动巡检服务状态、分析日志、修复 Bug。
# 每次巡检完成后，在 ./report/ 目录下生成一份 Markdown 修复报告。
#
# 用法:
#   ./scripts/patrol.sh          # 手动执行一次巡检
#   ./scripts/setup_patrol.sh    # 安装 cron 定时任务（每小时一次）
#
# 依赖:
#   - claude (Claude Code CLI) 已安装且在 PATH 中
# ============================================================================

set -euo pipefail

# ── 配置 ──
PROJECT_DIR="/home/bin.liang/Documents/03-open-source/NexusAgent/related_project/NetMind-AI-RS-NexusMatrix"
REPORT_DIR="${PROJECT_DIR}/report"
LOG_FILE="/tmp/nexus_matrix.log"
APP_LOG_DIR="${PROJECT_DIR}/logs"
CLAUDE_BIN="/home/bin.liang/.local/bin/claude"

# 生成时间戳
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
REPORT_FILE="${REPORT_DIR}/patrol_${TIMESTAMP}.md"

# 确保 report 目录存在
mkdir -p "${REPORT_DIR}"

# ── 检查 claude 是否可用 ──
if [ ! -x "${CLAUDE_BIN}" ]; then
    echo "[ERROR] Claude Code not found at ${CLAUDE_BIN}"
    exit 1
fi

# ── 构造 Prompt ──
# 这个 prompt 是给无界面 Claude Code 的完整任务描述
PROMPT="你是 NexusMatrix 服务的自动巡检员。请执行以下任务：

## 任务 1：检查服务状态
- 运行 \`ps aux | grep nexus_matrix\` 检查服务是否在运行
- 运行 \`curl -s http://localhost:8953/health\` 检查 HTTP 健康状态
- 如果服务没有运行，尝试在后台重启它：\`cd ${PROJECT_DIR} && python -m nexus_matrix.main > /tmp/nexus_matrix.log 2>&1 &\`

## 任务 2：分析日志
- 读取 access log: \`tail -200 ${LOG_FILE}\`
- 读取 app log: 找到 ${APP_LOG_DIR} 下最新的 log 文件并读取最后 200 行
- 统计 HTTP 状态码分布（200/400/401/422/500 各多少）
- 找出所有 422 和 500 错误的详细信息

## 任务 3：修复 Bug
- 如果发现 422 错误，检查日志中的 '422 验证错误' 行，分析 Agent 发送了什么格式
- 如果发现 500 错误，读取对应的源代码，找到根因并修复
- 如果发现服务不稳定（频繁 401），检查 token 和认证链路
- 修复后如果需要重启服务，先 kill 旧进程再启动新进程

## 任务 4：检查 Agent 交互
- 查看数据库中的 agent 数量：\`sqlite3 ${PROJECT_DIR}/data/nexus_matrix.db 'SELECT count(*) FROM agents WHERE status=\"active\"'\`
- 查看最近的消息是否正常投递

## 任务 6：处理 Agent 反馈
- 调用 GET /api/v1/feedback/unresolved 获取所有未解决的反馈（需要带 X-Api-Key 请求头）
- 根据反馈内容分析问题、定位代码、修复 Bug
- 修复后调用 PUT /api/v1/feedback/{id}/resolve 标记为已解决，附上 resolution 说明
- 如果是功能建议（suggestion），只记录在报告中，不自动处理

## 任务 5：写报告
完成以上所有任务后，将巡检报告写入 ${REPORT_FILE}，格式如下：

\`\`\`markdown
# NexusMatrix Patrol Report — ${TIMESTAMP}

## Service Status
- Running: yes/no
- Health: ok/error
- PID: xxx
- Uptime: xxx

## Log Analysis
- Total requests since last check: N
- Status distribution: 200: N, 422: N, 500: N, ...
- Error details: (如有)

## Issues Found & Fixed
1. (issue description) -> (fix applied)
2. ...

## Agent Activity
- Active agents: N
- Recent messages: N in last hour

## Agent Feedback
- Unresolved: N
- Resolved this patrol: N
- Details: (feedback summaries and actions taken)

## Recommendations
- (任何需要人工介入的问题)
\`\`\`

重要：
- 只修复你有把握的 bug，不确定的只记录在报告中
- 如果一切正常，报告中简单说明即可
- 报告用英文写
- **绝对不要调用 POST /api/v1/registry/register 注册新 agent！** 你是巡检员，不是用户。直接查数据库即可，不需要 API key。
"

# ── 执行巡检 ──
echo "[$(date)] Starting NexusMatrix patrol..."

cd "${PROJECT_DIR}"

# 无界面模式启动 Claude Code
# --dangerously-skip-permissions: 允许自动执行命令（巡检脚本需要）
# -p: 传入 prompt
# --max-turns: 限制最大交互轮数，防止死循环
"${CLAUDE_BIN}" \
    -p "${PROMPT}" \
    --dangerously-skip-permissions \
    --max-turns 30 \
    2>&1 | tee "/tmp/patrol_${TIMESTAMP}.log"

echo "[$(date)] Patrol complete. Report: ${REPORT_FILE}"

# ── 清理旧报告（保留最近 30 份）──
cd "${REPORT_DIR}"
ls -t patrol_*.md 2>/dev/null | tail -n +31 | xargs -r rm -f

echo "[$(date)] Done."
