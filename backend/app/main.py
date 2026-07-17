import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import get_db
from app.ai.skills import registry
from app.api.routes import projects, sources, tasks, artifacts, workflow

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", description="小学单课时 AI 备课、可追溯 RAG、版本化产物与双包导出")
app.add_middleware(CORSMiddleware, allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"HTTP_{exc.status_code}", "message": exc.detail, "trace_id": request.state.trace_id}})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用，请凭 trace_id 排查", "trace_id": request.state.trace_id}})


@app.get("/health")
def health():
    return {"status": "ok", "service": "backend", "version": app.version}


@app.get("/health/db")
def health_db():
    db = next(get_db())
    try:
        db.execute(text("SELECT 1")); return {"status": "ok", "database": "mysql"}
    except Exception:
        raise HTTPException(503, "MySQL 暂时不可用")
    finally: db.close()


@app.get("/api/skills")
def skills(): return registry()


app.include_router(projects.router)
app.include_router(sources.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(workflow.router)

