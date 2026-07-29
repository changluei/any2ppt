"""FastAPI 应用入口。

本模块只负责应用级装配：启动时修复/初始化持久化状态、注册跨域与 trace_id
中间件、统一异常响应，以及挂载各业务路由。具体业务规则应留在 services/，
避免路由层和应用入口逐渐演变成难以测试的“大函数”。
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.ai.skills import registry
from app.ai.schemas import LessonContext
from app.ai.vector_store import ProjectVectorStore
from app.api.routes import artifacts, editor_agent, images, knowledge_bases, projects, sources, tasks, workflow
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.recovery_service import recover_interrupted_work
from app.services.knowledge_base_service import ensure_knowledge_bases
from app.services.source_service import migrate_legacy_personal_indexes
from app.schemas.api import ThemeRecommendationRequest
from app.services.theme_service import public_themes, select_theme

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """在开始接收请求前准备四类知识库，并恢复异常中断的后台任务。

    这些操作刻意放在路由注册之外，因此无论由 Uvicorn、测试客户端还是
    Docker 启动，服务都能获得一致的初始状态。
    """
    with SessionLocal() as db:
        ensure_knowledge_bases(db)
    migrate_legacy_personal_indexes()
    recover_interrupted_work()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="小学单课时 AI 备课、可追溯 RAG、版本化课件与 PPTX 导出服务。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _trace_id(request: Request) -> str:
    """返回当前请求的链路标识；异常发生得过早时生成一个兜底值。"""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """让前端报错、后端日志和 AI 调用可以用同一个 X-Trace-ID 串联。"""
    request.state.trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    """把 FastAPI 的多种 HTTPException detail 写法归一成前端约定的 error。"""
    detail = exc.detail
    if isinstance(detail, dict):
        error = {
            "code": detail.get("code") or f"HTTP_{exc.status_code}",
            "message": detail.get("message") or detail.get("detail") or "请求失败",
            "trace_id": _trace_id(request),
        }
        for key in ("current_version", "details", "blockers", "source_ids"):
            if key in detail:
                error[key] = detail[key]
    else:
        error = {"code": f"HTTP_{exc.status_code}", "message": str(detail), "trace_id": _trace_id(request)}
    return JSONResponse(status_code=exc.status_code, content={"error": error})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """保留 Pydantic 的字段级错误，同时使用统一错误信封。"""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "details": exc.errors(),
                "trace_id": _trace_id(request),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """隐藏内部异常细节，仅向客户端暴露可用于排障的 trace_id。"""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务暂时不可用，请凭 trace_id 排查",
                "trace_id": _trace_id(request),
            }
        },
    )


@app.get("/health")
def health():
    """无需外部依赖的存活探针。"""
    return {"status": "ok", "service": "backend", "version": app.version}


@app.get("/health/db")
def health_db():
    """执行最小 SQL，验证 MySQL/测试 SQLite 的连接确实可用。"""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = "sqlite" if settings.database_url.startswith("sqlite") else "mysql"
        return {"status": "ok", "database": database}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_ERROR", "message": "数据库暂时不可用，请稍后重试"},
        ) from exc


@app.get("/health/ai")
def health_ai():
    """报告 DeepSeek 是否已配置；degraded 不代表后端整体不可用。"""
    configured = bool(settings.deepseek_api_key.strip()) and not settings.ai_force_fallback
    return {
        "status": "ok" if configured else "degraded",
        "provider": "deepseek",
        "configured": configured,
        "forced_fallback": settings.ai_force_fallback,
        "model": settings.deepseek_model,
    }


@app.get("/health/chroma")
def health_chroma():
    """报告向量库实现；缺少 Chroma 时开发环境会显示 JSON 兜底。"""
    store = ProjectVectorStore()
    return {
        "status": "ok",
        "path": str(store.root),
        "backend": "chromadb" if store.client else "json-fallback",
    }


@app.get("/api/skills")
def skills():
    """公开生成流水线中可用的教学技能注册表。"""
    return registry()


@app.get("/api/themes")
def themes():
    """返回首页主题卡片需要的脱敏主题元数据。"""
    return public_themes()


@app.post("/api/themes/recommend")
def recommend_theme(data: ThemeRecommendationRequest):
    """依据课题上下文推荐主题，但不会在此时下载或安装主题。"""
    return select_theme(
        LessonContext(
            project_id="theme-preview",
            subject=data.subject or "未指定学科",
            grade=data.grade or "未指定年级",
            lesson_topic=data.lesson_topic or "未指定课题",
            student_profile=data.student_profile,
            teacher_requirements=data.teacher_requirements,
        )
    )


app.include_router(projects.router)
app.include_router(sources.router)
app.include_router(knowledge_bases.router)
app.include_router(images.router)
app.include_router(editor_agent.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(workflow.router)
