"""Course-scoped draft authoring; all writes lock course before domain."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.courses import get_course, owned_course_for_update
from app.database import get_session
from app.domain_schemas import (
    CompetencyCreate, CompetencyPage, CompetencyRead, CompetencyUpdate,
    DomainVersionCreate, DomainVersionPage, DomainVersionRead,
    SkillCreate, SkillPage, SkillRead, SkillUpdate,
)
from app.identity import Principal
from app.models import Competency, DomainVersion, Skill
from app.security import require_api_key, require_author

router = APIRouter(
    prefix="/courses/{course_id}/domain-versions", tags=["domain authoring"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid credentials"},
               403: {"description": "Role or course ownership denied"},
               404: {"description": "Resource not found in requested parent"},
               409: {"description": "Duplicate code, archived course, or immutable domain"},
               503: {"description": "Database operation unavailable"}},
)


def version_path(course_id, version_id):
    return "/api/v1/courses/{}/domain-versions/{}".format(course_id, version_id)


def active_owned_course(course_id, principal, session):
    course = owned_course_for_update(course_id, principal, session)
    if course.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived courses cannot be authored")
    return course


def load_version(course_id, domain_version_id, session, principal=None):
    if principal is not None:
        active_owned_course(course_id, principal, session)
    else:
        get_course(course_id, session)
    query = select(DomainVersion).where(
        DomainVersion.id == str(domain_version_id), DomainVersion.course_id == str(course_id),
    )
    if principal is not None:
        query = query.with_for_update()
    version = session.scalar(query)
    if version is None:
        raise HTTPException(status_code=404, detail="Domain version not found in this course")
    if principal is not None and version.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft domains can be authored")
    return version


def load_child(model, resource_id, domain_version_id, session):
    item = session.scalar(select(model).where(
        model.id == str(resource_id), model.domain_version_id == str(domain_version_id),
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Resource not found in this domain version")
    return item


def commit_resource(session, item):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="Code or version already exists in this parent") from exc
        raise
    session.refresh(item)
    return item


@router.post("", response_model=DomainVersionRead, status_code=201)
def create_domain_version(
    course_id: UUID, payload: DomainVersionCreate, response: Response,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    active_owned_course(course_id, principal, session)
    # The course lock serializes version allocation, authoring and archival.
    latest = session.scalar(select(func.max(DomainVersion.version)).where(DomainVersion.course_id == str(course_id)))
    version = DomainVersion(course_id=str(course_id), version=(latest or 0) + 1)
    session.add(version)
    commit_resource(session, version)
    response.headers["Location"] = version_path(course_id, version.id)
    return version


@router.get("", response_model=DomainVersionPage)
def list_domain_versions(
    course_id: UUID, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    get_course(course_id, session)
    items = session.scalars(select(DomainVersion).where(DomainVersion.course_id == str(course_id))
                            .order_by(DomainVersion.version).limit(limit).offset(offset)).all()
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/{domain_version_id}", response_model=DomainVersionRead)
def get_domain_version(course_id: UUID, domain_version_id: UUID, session: Session = Depends(get_session)):
    return load_version(course_id, domain_version_id, session)


@router.post("/{domain_version_id}/competencies", response_model=CompetencyRead, status_code=201)
def create_competency(
    course_id: UUID, domain_version_id: UUID, payload: CompetencyCreate, response: Response,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session, principal)
    item = Competency(domain_version_id=str(domain_version_id), **payload.model_dump())
    session.add(item)
    commit_resource(session, item)
    response.headers["Location"] = version_path(course_id, domain_version_id) + "/competencies/" + item.id
    return item


@router.get("/{domain_version_id}/competencies", response_model=CompetencyPage)
def list_competencies(
    course_id: UUID, domain_version_id: UUID,
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session)
    items = session.scalars(select(Competency).where(Competency.domain_version_id == str(domain_version_id))
                            .order_by(Competency.code).limit(limit).offset(offset)).all()
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/{domain_version_id}/competencies/{competency_id}", response_model=CompetencyRead)
def get_competency(course_id: UUID, domain_version_id: UUID, competency_id: UUID, session: Session = Depends(get_session)):
    load_version(course_id, domain_version_id, session)
    return load_child(Competency, competency_id, domain_version_id, session)


@router.patch("/{domain_version_id}/competencies/{competency_id}", response_model=CompetencyRead)
def update_competency(
    course_id: UUID, domain_version_id: UUID, competency_id: UUID, payload: CompetencyUpdate,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session, principal)
    item = load_child(Competency, competency_id, domain_version_id, session)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, name, value)
    return commit_resource(session, item)


@router.post("/{domain_version_id}/skills", response_model=SkillRead, status_code=201)
def create_skill(
    course_id: UUID, domain_version_id: UUID, payload: SkillCreate, response: Response,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session, principal)
    load_child(Competency, payload.competency_id, domain_version_id, session)
    item = Skill(domain_version_id=str(domain_version_id), **payload.model_dump(mode="json"))
    session.add(item)
    commit_resource(session, item)
    response.headers["Location"] = version_path(course_id, domain_version_id) + "/skills/" + item.id
    return item


@router.get("/{domain_version_id}/skills", response_model=SkillPage)
def list_skills(
    course_id: UUID, domain_version_id: UUID,
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session)
    items = session.scalars(select(Skill).where(Skill.domain_version_id == str(domain_version_id))
                            .order_by(Skill.code).limit(limit).offset(offset)).all()
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/{domain_version_id}/skills/{skill_id}", response_model=SkillRead)
def get_skill(course_id: UUID, domain_version_id: UUID, skill_id: UUID, session: Session = Depends(get_session)):
    load_version(course_id, domain_version_id, session)
    return load_child(Skill, skill_id, domain_version_id, session)


@router.patch("/{domain_version_id}/skills/{skill_id}", response_model=SkillRead)
def update_skill(
    course_id: UUID, domain_version_id: UUID, skill_id: UUID, payload: SkillUpdate,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    load_version(course_id, domain_version_id, session, principal)
    item = load_child(Skill, skill_id, domain_version_id, session)
    values = payload.model_dump(exclude_unset=True)
    kind = values.get("skill_kind", item.skill_kind)
    automaticity = values.get("requires_automaticity", item.requires_automaticity)
    if kind == "non_routine" and automaticity:
        raise HTTPException(status_code=422, detail="Only routine skills can require automaticity")
    for name, value in values.items():
        setattr(item, name, value)
    return commit_resource(session, item)
