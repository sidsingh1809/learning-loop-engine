from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.catalog import router as catalog_router
from app.courses import router as courses_router
from app.database import get_session
from app.domains import router as domains_router
from app.learners import router as learners_router
from app.plans import router as plans_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # Fail at startup when credentials or configuration are missing.
    yield


app = FastAPI(
    title="Learning Loop Engine API",
    version="0.7.0",
    description="Day 7 deterministic, explainable next-action plans over published domains and reviewed synthetic catalogs. Activity generation remains planned.",
    lifespan=lifespan,
)
app.include_router(courses_router, prefix="/api/v1")
app.include_router(domains_router, prefix="/api/v1")
app.include_router(learners_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(plans_router, prefix="/api/v1")


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
    session.execute(text("SELECT id, course_id, version, status, published_at FROM domain_versions LIMIT 1"))
    session.execute(text("SELECT id, domain_version_id, code, statement FROM competencies LIMIT 1"))
    session.execute(text("SELECT id, domain_version_id, competency_id, skill_kind, requires_automaticity FROM skills LIMIT 1"))
    session.execute(text("SELECT id, domain_version_id, skill_id, prerequisite_skill_id FROM skill_prerequisites LIMIT 1"))
    session.execute(text("SELECT id, principal_subject, created_at FROM learners LIMIT 1"))
    session.execute(text("SELECT id, learner_id, course_id, domain_version_id, status FROM enrollments LIMIT 1"))
    session.execute(text("SELECT enrollment_id, skill_id, domain_version_id, band, evidence_count, revision, updated_at FROM learner_skill_states LIMIT 1"))
    session.execute(text("SELECT id, category, version, rules, review_status FROM policy_versions LIMIT 1"))
    session.execute(text("SELECT id, activity_type, version, learning_science_policy_id, safety_policy_id, review_status FROM activity_variants LIMIT 1"))
    session.execute(text("SELECT activity_variant_id, component, rationale FROM component_activity_mappings LIMIT 1"))
    session.execute(text("SELECT id, enrollment_id, input_fingerprint, input_snapshot, decision FROM loop_plans LIMIT 1"))
    session.execute(text("SELECT loop_plan_id, position, activity_variant_id, components FROM loop_steps LIMIT 1"))
    return {"status": "ready"}
