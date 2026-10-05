from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.identity import Principal
from app.learner_schemas import (EnrollmentCreate, EnrollmentPage, EnrollmentRead, LearnerCreate,
                                 LearnerRead, LearnerStateRead, SkillStateRead)
from app.models import Course, DomainVersion, Enrollment, Learner, LearnerSkillState, Skill
from app.security import require_learner

router = APIRouter(
    prefix="/learners", tags=["learners"], dependencies=[Depends(require_learner)],
    responses={401: {"description": "Missing or invalid credentials"},
               403: {"description": "Learner role required"},
               404: {"description": "Record not found or not accessible"},
               409: {"description": "Enrollment conflict or unavailable course/domain"},
               503: {"description": "Database operation unavailable"}},
)


@router.post("", response_model=LearnerRead, status_code=201,
             responses={200: {"model": LearnerRead, "description": "Existing learner returned"}})
def create_learner(payload: LearnerCreate, response: Response,
                   principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    learner = session.scalar(select(Learner).where(Learner.principal_subject == principal.subject))
    if learner is None:
        learner = Learner(principal_subject=principal.subject)
        session.add(learner)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if getattr(exc.orig, "args", (None,))[0] != 1062:
                raise
            # Concurrent registration of the same identity returns the existing row.
            learner = session.scalar(select(Learner).where(Learner.principal_subject == principal.subject))
            if learner is None:
                raise
            response.status_code = 200
        session.refresh(learner)
    else:
        response.status_code = 200
    response.headers["Location"] = "/api/v1/learners/" + learner.id
    return learner


def own_learner(learner_id: UUID, principal: Principal, session: Session) -> Learner:
    learner = session.scalar(select(Learner).where(
        Learner.id == str(learner_id), Learner.principal_subject == principal.subject))
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return learner


@router.get("/{learner_id}", response_model=LearnerRead)
def get_learner(learner_id: UUID, principal: Principal = Depends(require_learner),
                session: Session = Depends(get_session)):
    return own_learner(learner_id, principal, session)


@router.post("/{learner_id}/enrollments", response_model=EnrollmentRead, status_code=201,
             responses={200: {"model": EnrollmentRead, "description": "Existing enrollment returned"}})
def create_enrollment(learner_id: UUID, payload: EnrollmentCreate, response: Response,
                      principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    own_learner(learner_id, principal, session)
    # Same lock order as course archival and domain publication.
    course = session.scalar(select(Course).where(Course.id == str(payload.course_id)).with_for_update())
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    domain = session.scalar(select(DomainVersion).where(
        DomainVersion.id == str(payload.domain_version_id), DomainVersion.course_id == course.id).with_for_update())
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain version not found")
    if course.archived_at is not None or domain.status != "published":
        raise HTTPException(status_code=409, detail="Enrollment requires an active course and published domain")
    existing = session.scalar(select(Enrollment).where(
        Enrollment.learner_id == str(learner_id), Enrollment.course_id == course.id).with_for_update())
    if existing is not None:
        if existing.domain_version_id != domain.id:
            raise HTTPException(status_code=409, detail="Learner is already enrolled in another version of this course")
        response.status_code = 200
        enrollment = existing
    else:
        enrollment = Enrollment(learner_id=str(learner_id), course_id=course.id, domain_version_id=domain.id)
        session.add(enrollment)
        session.flush()
        # Use a current read if publication completed after the initial identity lookup.
        skills = session.scalars(select(Skill).where(Skill.domain_version_id == domain.id).with_for_update()).all()
        session.add_all([LearnerSkillState(enrollment_id=enrollment.id, domain_version_id=domain.id, skill_id=skill.id)
                         for skill in skills])
        # Enrollment and every initial skill state commit together.
        session.commit()
        session.refresh(enrollment)
    response.headers["Location"] = "/api/v1/learners/{}/enrollments/{}".format(learner_id, enrollment.id)
    return enrollment


@router.get("/{learner_id}/enrollments", response_model=EnrollmentPage)
def list_enrollments(learner_id: UUID, limit: int = Query(default=20, ge=1, le=100),
                     offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_learner),
                     session: Session = Depends(get_session)):
    own_learner(learner_id, principal, session)
    items = session.scalars(select(Enrollment).where(Enrollment.learner_id == str(learner_id))
                            .order_by(Enrollment.created_at, Enrollment.id).limit(limit).offset(offset)).all()
    return EnrollmentPage(items=[EnrollmentRead.model_validate(item) for item in items], limit=limit, offset=offset)


def own_enrollment(learner_id: UUID, enrollment_id: UUID, principal: Principal, session: Session) -> Enrollment:
    own_learner(learner_id, principal, session)
    enrollment = session.scalar(select(Enrollment).where(
        Enrollment.id == str(enrollment_id), Enrollment.learner_id == str(learner_id)))
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


@router.get("/{learner_id}/enrollments/{enrollment_id}", response_model=EnrollmentRead)
def get_enrollment(learner_id: UUID, enrollment_id: UUID, principal: Principal = Depends(require_learner),
                   session: Session = Depends(get_session)):
    return own_enrollment(learner_id, enrollment_id, principal, session)


@router.get("/{learner_id}/enrollments/{enrollment_id}/state", response_model=LearnerStateRead)
def get_state(learner_id: UUID, enrollment_id: UUID, limit: int = Query(default=20, ge=1, le=100),
              offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_learner),
              session: Session = Depends(get_session)):
    enrollment = own_enrollment(learner_id, enrollment_id, principal, session)
    states = session.scalars(select(LearnerSkillState).join(Skill, Skill.id == LearnerSkillState.skill_id)
                             .where(LearnerSkillState.enrollment_id == enrollment.id)
                             .order_by(Skill.code, Skill.id).limit(limit).offset(offset)).all()
    return LearnerStateRead(enrollment_id=enrollment.id, domain_version_id=enrollment.domain_version_id,
                            items=[SkillStateRead.model_validate(state) for state in states], limit=limit, offset=offset)
