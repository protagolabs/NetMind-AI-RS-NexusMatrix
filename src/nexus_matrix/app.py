"""
@file_name: app.py
@author: Bin Liang
@date: 2026-03-03
@description: FastAPI 应用工厂

创建和配置 FastAPI 应用实例，
包括中间件、路由挂载、生命周期管理。
"""

import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

# 匹配无效 JSON 转义序列（\后跟非法字符，且前面不是另一个\）
# 合法的 JSON 转义: \" \\ \/ \b \f \n \r \t \uXXXX
# 负向后瞻确保不误处理 \\! 这种合法的 "字面反斜杠+字符" 组合
_INVALID_JSON_ESCAPE_RE = re.compile(r'(?<!\\)\\([^"\\/bfnrtu])')

from nexus_matrix.api.deps import container
from nexus_matrix.api.v1.router import router as v1_router
from nexus_matrix.config import get_settings

# JSON 安全的原始类型集合
_JSON_PRIMITIVES = (str, int, float, bool, type(None))


def _make_json_safe(obj):
    """递归将任意对象转为 JSON 可序列化的结构。

    dict/list 递归处理，JSON 原始类型保持不变，
    其他类型（tuple, ValueError, Exception 等）一律 str() 转换。
    """
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(item) for item in obj]
    if isinstance(obj, _JSON_PRIMITIVES):
        return obj
    return str(obj)


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


class JsonEscapeSanitizerMiddleware(BaseHTTPMiddleware):
    """修复请求体中无效的 JSON 转义序列。

    部分 Agent（尤其是 LLM 生成的 JSON）会错误地对 Matrix room ID 中的
    '!' 进行转义，发送 '\\!' 这样的无效 JSON 转义。此中间件在 JSON 解析
    之前拦截请求体，将无效转义还原为原始字符。

    仅对 Content-Type 为 application/json 的 POST/PUT/PATCH 请求生效。
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        content_type = request.headers.get("content-type", "")
        if (
            request.method in ("POST", "PUT", "PATCH")
            and "application/json" in content_type
        ):
            body = await request.body()
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                return await call_next(request)

            sanitized = _INVALID_JSON_ESCAPE_RE.sub(r'\1', text)
            if sanitized != text:
                logger.debug(
                    f"JSON 转义修复 [{request.method} {request.url.path}]: "
                    f"修复了无效转义序列"
                )
                # 用修复后的 body 替换原始请求体
                request._body = sanitized.encode("utf-8")

        return await call_next(request)


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

    # JSON 容错中间件 — 修复 Agent 发送的无效 JSON 转义序列（如 \! → !）
    # 必须在 CORS 之前添加，使其在请求处理链中更早生效
    app.add_middleware(JsonEscapeSanitizerMiddleware)

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
        # 递归将所有非 JSON 原生类型转为字符串，彻底避免序列化失败
        safe_errors = [_make_json_safe(err) for err in exc.errors()]
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
