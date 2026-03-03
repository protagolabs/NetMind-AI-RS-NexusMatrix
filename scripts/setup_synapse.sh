#!/bin/bash
# ============================================================
# NexusMatrix - Synapse Homeserver 初始化脚本
#
# 功能：
#   1. 生成 Synapse 签名密钥
#   2. 创建管理员用户
#   3. 验证服务状态
#
# 使用方法:
#   chmod +x scripts/setup_synapse.sh
#   ./scripts/setup_synapse.sh
# ============================================================

set -euo pipefail

# 配置
SYNAPSE_URL="${SYNAPSE_URL:-http://localhost:8008}"
ADMIN_USER="${ADMIN_USER:-nexus_admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-nexus_admin_pass_2026}"
SHARED_SECRET="${SHARED_SECRET:-nexus-shared-secret}"

echo "=== NexusMatrix Synapse Setup ==="
echo ""

# 检查 Synapse 是否就绪
echo "[1/3] Checking Synapse health..."
MAX_RETRIES=30
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sf "${SYNAPSE_URL}/health" > /dev/null 2>&1; then
        echo "  Synapse is healthy!"
        break
    fi
    RETRY=$((RETRY + 1))
    echo "  Waiting for Synapse... (${RETRY}/${MAX_RETRIES})"
    sleep 2
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "ERROR: Synapse did not start in time"
    exit 1
fi

# 注册管理员用户
echo ""
echo "[2/3] Registering admin user: ${ADMIN_USER}"
python3 scripts/create_admin.py \
    --homeserver "${SYNAPSE_URL}" \
    --shared-secret "${SHARED_SECRET}" \
    --username "${ADMIN_USER}" \
    --password "${ADMIN_PASSWORD}" \
    --admin

echo ""
echo "[3/3] Verifying admin login..."
# 验证登录
LOGIN_RESULT=$(curl -sf -X POST "${SYNAPSE_URL}/_matrix/client/v3/login" \
    -H "Content-Type: application/json" \
    -d "{\"type\": \"m.login.password\", \"user\": \"${ADMIN_USER}\", \"password\": \"${ADMIN_PASSWORD}\"}" \
    2>/dev/null)

if echo "${LOGIN_RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['user_id'])" 2>/dev/null; then
    echo "  Admin login verified!"
else
    echo "  WARNING: Admin login verification failed (user may already exist)"
fi

echo ""
echo "=== Setup Complete ==="
echo "  Synapse:      ${SYNAPSE_URL}"
echo "  Admin User:   @${ADMIN_USER}:localhost"
echo "  NexusMatrix:  http://localhost:8900/docs"
