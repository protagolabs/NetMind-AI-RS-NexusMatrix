# NexusMatrix Service Dockerfile
# 多阶段构建，优化镜像大小和构建速度

# ── 阶段 1: 构建依赖 ──
FROM python:3.11-slim as builder

WORKDIR /app

# 安装系统依赖（用于编译 Python 扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml .
COPY src/ src/

# 安装 Python 依赖到虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ── 阶段 2: 运行时镜像 ──
FROM python:3.11-slim as runtime

WORKDIR /app

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制源代码
COPY src/ src/

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs

# 非 root 用户运行
RUN useradd --create-home --shell /bin/bash nexus
RUN chown -R nexus:nexus /app
USER nexus

# 环境变量
ENV NEXUS_HOST=0.0.0.0
ENV NEXUS_PORT=8900
ENV NEXUS_DATABASE_PATH=/app/data/nexus_matrix.db

EXPOSE 8900

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8900/health'); r.raise_for_status()" || exit 1

# 启动命令
CMD ["python", "-m", "nexus_matrix.main"]
