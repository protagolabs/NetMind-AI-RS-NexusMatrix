#!/usr/bin/env bash
# ============================================================================
# Setup NexusMatrix Auto-Patrol Cron Job
#
# 安装每小时自动巡检的 cron 任务。
#
# 用法:
#   ./scripts/setup_patrol.sh           # 安装 cron
#   ./scripts/setup_patrol.sh remove    # 移除 cron
#   ./scripts/setup_patrol.sh status    # 查看当前状态
# ============================================================================

set -euo pipefail

PROJECT_DIR="/home/bin.liang/Documents/03-open-source/NexusAgent/related_project/NetMind-AI-RS-NexusMatrix"
PATROL_SCRIPT="${PROJECT_DIR}/scripts/patrol.sh"
CRON_LOG="/tmp/nexus_patrol_cron.log"

# cron 表达式：每小时整点执行
CRON_EXPR="0 * * * *"
CRON_CMD="${CRON_EXPR} ${PATROL_SCRIPT} >> ${CRON_LOG} 2>&1"
CRON_MARKER="# NexusMatrix Auto-Patrol"

case "${1:-install}" in
    install)
        # 确保脚本可执行
        chmod +x "${PATROL_SCRIPT}"

        # 检查是否已安装
        if crontab -l 2>/dev/null | grep -q "${CRON_MARKER}"; then
            echo "Cron job already installed. Use 'remove' first to reinstall."
            crontab -l | grep "${CRON_MARKER}" -A1
            exit 0
        fi

        # 添加到 crontab
        (crontab -l 2>/dev/null || true; echo "${CRON_MARKER}"; echo "${CRON_CMD}") | crontab -

        echo "Cron job installed successfully!"
        echo ""
        echo "  Schedule: Every hour at :00"
        echo "  Script:   ${PATROL_SCRIPT}"
        echo "  Log:      ${CRON_LOG}"
        echo "  Reports:  ${PROJECT_DIR}/report/"
        echo ""
        echo "Verify with: crontab -l | grep nexus"
        echo "Manual run:  ${PATROL_SCRIPT}"
        ;;

    remove)
        if crontab -l 2>/dev/null | grep -q "${CRON_MARKER}"; then
            crontab -l | grep -v "${CRON_MARKER}" | grep -v "${PATROL_SCRIPT}" | crontab -
            echo "Cron job removed."
        else
            echo "No cron job found."
        fi
        ;;

    status)
        echo "=== Cron Status ==="
        if crontab -l 2>/dev/null | grep -q "${CRON_MARKER}"; then
            echo "Status: ACTIVE"
            crontab -l | grep "${CRON_MARKER}" -A1
        else
            echo "Status: NOT INSTALLED"
        fi

        echo ""
        echo "=== Recent Reports ==="
        ls -lt "${PROJECT_DIR}/report/patrol_"*.md 2>/dev/null | head -5 || echo "No reports yet."

        echo ""
        echo "=== Recent Cron Log ==="
        tail -10 "${CRON_LOG}" 2>/dev/null || echo "No cron log yet."
        ;;

    *)
        echo "Usage: $0 [install|remove|status]"
        exit 1
        ;;
esac
