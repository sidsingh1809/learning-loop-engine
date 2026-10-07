"""Immutable global catalog versions; an instructor reviews synthetic use only."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.catalog_schemas import (
    ActivityCreate, ActivityPage, ActivityRead, ActivityType, Component,
    PolicyCategory, PolicyCreate, PolicyPage, PolicyRead, ReviewInput, ReviewStatus,
)
from app.database import get_session
from app.identity import Principal, Role
from app.models import ActivityVariant, ComponentActivityMapping, PolicyVersion, utc_now
from app.security import require_api_key, require_author

router = APIRouter(prefix="/catalog", tags=["activity and policy catalog"], dependencies=[Depends(require_api_key)],
                   responses={401: {"description": "Missing or invalid credentials"},
                              403: {"description": "Role or ownership denied"},
                              404: {"description": "Version not found or not approved"},
                              409: {"description": "Duplicate version or incompatible review transition"},
                              503: {"description": "Database operation unavailable"}})


def require_catalog_editor(principal: Principal = Depends(require_api_key)) -> Principal:
    if not principal.roles & {Role.author, Role.instructor}:
        raise HTTPException(status_code=403, detail="Author or instructor role required")
    return principal


def require_catalog_reviewer(principal: Principal = Depends(require_api_key)) -> Principal:
    if Role.instructor not in principal.roles:
        raise HTTPException(status_code=403, detail="Instructor role required")
    return principal


def catalog_query(model, principal=None):
    query = select(model)
    if model is ActivityVariant:
        query = query.options(selectinload(ActivityVariant.mappings))
    if principal is None:
        query = query.where(model.review_status == "approved")
    elif Role.instructor not in principal.roles:
        query = query.where(model.created_by == principal.subject)
    return query


def load_version(model, version_id, session, principal=None, lock=False):
    query = catalog_query(model, principal).where(model.id == str(version_id))
    if lock:
        query = query.with_for_update()
    item = session.scalar(query)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalog version not found")
    return item


def commit_version(session, item):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="Catalog code and version already exist") from exc
        raise
    session.refresh(item)
    return item


def approved_policy(session, policy_id, category):
    policy = load_version(PolicyVersion, policy_id, session)
    if policy.category != category:
        raise HTTPException(status_code=422, detail="Referenced policy has the wrong category")
    return policy


def review_version(model, version_id, payload, principal, session):
    item = load_version(model, version_id, session, principal, lock=True)
    if item.created_by == principal.subject:
        raise HTTPException(status_code=403, detail="Creators cannot review their own catalog version")
    if item.review_status != "draft":
        if (item.review_status, item.reviewed_by, item.review_note) == (payload.decision, principal.subject, payload.note):
            return item
        raise HTTPException(status_code=409, detail="Reviewed catalog versions are immutable; create a new version")
    if model is ActivityVariant and payload.decision == "approved":
        approved_policy(session, item.learning_science_policy_id, "learning_science")
        approved_policy(session, item.safety_policy_id, "safety")
    item.review_status = payload.decision
    item.reviewed_by = principal.subject
    item.review_note = payload.note
    item.reviewed_at = utc_now()
    return commit_version(session, item)


def page(session, model, limit, offset, principal=None, status=None, category=None, activity_type=None, component=None):
    query = catalog_query(model, principal)
    if status is not None:
        query = query.where(model.review_status == status)
    if category is not None:
        query = query.where(PolicyVersion.category == category)
    if activity_type is not None:
        query = query.where(ActivityVariant.activity_type == activity_type)
    if component is not None:
        query = query.where(ActivityVariant.mappings.any(ComponentActivityMapping.component == component))
    items = session.scalars(query.order_by(model.code, model.version, model.id).limit(limit).offset(offset)).all()
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/policy-versions", response_model=PolicyRead, status_code=201)
def create_policy(payload: PolicyCreate, response: Response, principal: Principal = Depends(require_author),
                  session: Session = Depends(get_session)):
    item = PolicyVersion(**payload.model_dump(mode="json"), created_by=principal.subject)
    session.add(item)
    commit_version(session, item)
    response.headers["Location"] = "/api/v1/catalog/policy-versions/" + item.id
    return item


@router.get("/policy-versions", response_model=PolicyPage)
def list_policy_versions(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                         status: ReviewStatus = Query(None), category: PolicyCategory = Query(None),
                         principal: Principal = Depends(require_catalog_editor), session: Session = Depends(get_session)):
    return page(session, PolicyVersion, limit, offset, principal, status, category)


@router.get("/policy-versions/{version_id}", response_model=PolicyRead)
def get_policy_version(version_id: UUID, principal: Principal = Depends(require_catalog_editor), session: Session = Depends(get_session)):
    return load_version(PolicyVersion, version_id, session, principal)


@router.post("/policy-versions/{version_id}/review", response_model=PolicyRead)
def review_policy(version_id: UUID, payload: ReviewInput, principal: Principal = Depends(require_catalog_reviewer),
                  session: Session = Depends(get_session)):
    return review_version(PolicyVersion, version_id, payload, principal, session)


@router.get("/policies", response_model=PolicyPage)
def list_policies(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  category: PolicyCategory = Query(None), session: Session = Depends(get_session)):
    return page(session, PolicyVersion, limit, offset, category=category)


@router.get("/policies/{version_id}", response_model=PolicyRead)
def get_policy(version_id: UUID, session: Session = Depends(get_session)):
    return load_version(PolicyVersion, version_id, session)


@router.post("/activity-versions", response_model=ActivityRead, status_code=201)
def create_activity(payload: ActivityCreate, response: Response, principal: Principal = Depends(require_author),
                    session: Session = Depends(get_session)):
    approved_policy(session, payload.learning_science_policy_id, "learning_science")
    approved_policy(session, payload.safety_policy_id, "safety")
    values = payload.model_dump(mode="json", exclude={"mappings"})
    item = ActivityVariant(**values, created_by=principal.subject,
                           mappings=[ComponentActivityMapping(**mapping.model_dump()) for mapping in payload.mappings])
    session.add(item)
    commit_version(session, item)
    response.headers["Location"] = "/api/v1/catalog/activity-versions/" + item.id
    return item


@router.get("/activity-versions", response_model=ActivityPage)
def list_activity_versions(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                           status: ReviewStatus = Query(None), principal: Principal = Depends(require_catalog_editor),
                           session: Session = Depends(get_session)):
    return page(session, ActivityVariant, limit, offset, principal, status)


@router.get("/activity-versions/{version_id}", response_model=ActivityRead)
def get_activity_version(version_id: UUID, principal: Principal = Depends(require_catalog_editor), session: Session = Depends(get_session)):
    return load_version(ActivityVariant, version_id, session, principal)


@router.post("/activity-versions/{version_id}/review", response_model=ActivityRead)
def review_activity(version_id: UUID, payload: ReviewInput, principal: Principal = Depends(require_catalog_reviewer),
                    session: Session = Depends(get_session)):
    return review_version(ActivityVariant, version_id, payload, principal, session)


@router.get("/activities", response_model=ActivityPage)
def list_activities(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                    activity_type: ActivityType = Query(None), component: Component = Query(None),
                    session: Session = Depends(get_session)):
    return page(session, ActivityVariant, limit, offset, activity_type=activity_type, component=component)


@router.get("/activities/{version_id}", response_model=ActivityRead)
def get_activity(version_id: UUID, session: Session = Depends(get_session)):
    return load_version(ActivityVariant, version_id, session)
