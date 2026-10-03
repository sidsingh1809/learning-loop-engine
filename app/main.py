from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.courses import router as courses_router
from app.database import get_session
from app.domains import router as domains_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # Fail at startup when credentials or configuration are missing.
    yield


app = FastAPI(
    title="Learning Loop Engine API",
    version="0.3.0",
    description="Day 3 draft domain versions, competencies and skills. Learning loop modules are planned.",
    lifespan=lifespan,
)
app.include_router(courses_router, prefix="/api/v1")
app.include_router(domains_router, prefix="/api/v1")


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request, exc):
    # Avoid returning connection strings, query parameters, or database internals.
    return JSONResponse(status_code=503, content={"detail": "Database operation unavailable"})


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready(session: Session = Depends(get_session)):
    # Query the migrated table: a bare SELECT 1 would hide a missing migration.
    session.execute(text("SELECT id, created_by, updated_at, archived_at FROM courses LIMIT 1"))
    session.execute(text("SELECT id, course_id, version, status FROM domain_versions LIMIT 1"))
    session.execute(text("SELECT id, domain_version_id, code, statement FROM competencies LIMIT 1"))
    session.execute(text("SELECT id, domain_version_id, competency_id, skill_kind, requires_automaticity FROM skills LIMIT 1"))
    return {"status": "ready"}
