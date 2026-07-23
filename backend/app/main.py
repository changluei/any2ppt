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
from app.api.routes import artifacts, images, projects, sources, tasks, workflow
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.recovery_service import recover_interrupted_work
from app.schemas.api import ThemeRecommendationRequest
from app.services.theme_service import public_themes, select_theme

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
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
    return {"status": "ok", "service": "backend", "version": app.version}


@app.get("/health/db")
def health_db():
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
    store = ProjectVectorStore()
    return {
        "status": "ok",
        "path": str(store.root),
        "backend": "chromadb" if store.client else "json-fallback",
    }


@app.get("/api/skills")
def skills():
    return registry()


@app.get("/api/themes")
def themes():
    return public_themes()


@app.post("/api/themes/recommend")
def recommend_theme(data: ThemeRecommendationRequest):
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
app.include_router(images.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(workflow.router)
