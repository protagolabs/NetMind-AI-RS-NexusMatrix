"""
@file_name: app.py
@author: Bin Liang
@date: 2026-03-03
@description: FastAPI 应用工厂

创建和配置 FastAPI 应用实例，
包括中间件、路由挂载、生命周期管理。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from nexus_matrix.api.deps import container
from nexus_matrix.api.v1.router import router as v1_router
from nexus_matrix.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时初始化所有服务，关闭时清理资源。
    """
    settings = get_settings()

    # 初始化服务容器
    logger.info("正在初始化 NexusMatrix 服务...")
    await container.init(settings)

    # 尝试初始化管理员客户端（连接到 Matrix homeserver）
    try:
        await container.client_manager.init_admin_client()
        logger.info("Matrix 管理员客户端已就绪")
    except Exception as e:
        logger.warning(
            f"Matrix 管理员客户端初始化失败（homeserver 可能未就绪）: {e}. "
            "服务将在无管理员权限的模式下运行。"
        )

    logger.info(f"NexusMatrix 服务已启动 - {settings.host}:{settings.port}")

    yield

    # 清理资源
    logger.info("正在关闭 NexusMatrix 服务...")
    await container.close()
    logger.info("NexusMatrix 服务已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    settings = get_settings()

    app = FastAPI(
        title="NexusMatrix",
        description=(
            "Matrix protocol service for NexusAgent ecosystem. "
            "Provides decentralized communication capabilities for AI agents, "
            "including room management, messaging, event sync, "
            "and centralized agent registry with semantic search."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 422 验证错误处理 — 记录请求 body 便于调试 Agent 发送的格式
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """记录 422 验证错误的请求详情，便于调试 Agent 发送的格式。"""
        body = None
        try:
            body = await request.body()
            body = body.decode("utf-8")[:500]
        except Exception:
            pass
        logger.warning(
            f"422 验证错误 [{request.method} {request.url.path}] "
            f"body={body} errors={exc.errors()}"
        )
        # 将 errors 中的 ValueError 对象转为字符串，避免 JSON 序列化失败
        safe_errors = []
        for err in exc.errors():
            safe_err = {k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                        for k, v in err.items()}
            if "ctx" in err and isinstance(err["ctx"], dict):
                safe_err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
            safe_errors.append(safe_err)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": safe_errors,
            },
        )

    # 全局异常处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """全局异常兜底处理。"""
        logger.error(f"未处理的异常: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                },
            },
        )

    # 挂载 v1 路由
    app.include_router(v1_router)

    # 健康检查端点
    @app.get("/health", tags=["System"])
    async def health_check():
        """服务健康检查。"""
        return {
            "status": "healthy",
            "service": "NexusMatrix",
            "version": "0.1.0",
        }

    # 根路径信息
    @app.get("/", tags=["System"])
    async def root():
        """服务信息。"""
        return {
            "service": "NexusMatrix",
            "version": "0.1.0",
            "description": "WeChat for AI Agents — decentralized communication over Matrix protocol",
            "docs": "/docs",
            "skill": "/skill.md",
            "heartbeat": "/heartbeat.md",
        }

    # ── Skill & Heartbeat 静态文档端点 ──
    # Agent 可直接 curl 获取使用说明

    _project_root = Path(__file__).resolve().parent.parent.parent

    @app.get("/skill.md", tags=["System"], response_class=PlainTextResponse)
    async def serve_skill_md():
        """Serve SKILL.md — full usage documentation for agents."""
        path = _project_root / "SKILL.md"
        if path.exists():
            return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")
        return PlainTextResponse("SKILL.md not found", status_code=404)

    @app.get("/heartbeat.md", tags=["System"], response_class=PlainTextResponse)
    async def serve_heartbeat_md():
        """Serve HEARTBEAT.md — periodic check-in instructions."""
        path = _project_root / "HEARTBEAT.md"
        if path.exists():
            return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")
        return PlainTextResponse("HEARTBEAT.md not found", status_code=404)

    return app
