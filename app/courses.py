from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.identity import Principal
from app.models import Course, utc_now
from app.schemas import CourseCreate, CoursePage, CourseRead, CourseUpdate
from app.security import require_api_key, require_author


router = APIRouter(
    prefix="/courses", tags=["courses"], dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid credentials"},
               403: {"description": "Role or course ownership denied"},
               404: {"description": "Course not found"},
               409: {"description": "Duplicate course code or archived course"},
               503: {"description": "Database operation unavailable"}},
)


@router.post("", response_model=CourseRead, status_code=201)
def create_course(
    payload: CourseCreate, response: Response,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    course = Course(**payload.model_dump(), created_by=principal.subject)
    session.add(course)
    commit_course(session, course)
    response.headers["Location"] = "/api/v1/courses/" + course.id
    return course


def commit_course(session: Session, course: Course) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # MySQL error 1062 is the duplicate key error; other integrity failures are bugs.
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="Course code already exists") from exc
        raise
    # Return the persisted representation, including MySQL's timestamp precision.
    session.refresh(course)


@router.get("", response_model=CoursePage)
def list_courses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Literal["active", "archived", "all"] = Query(default="active"),
    session: Session = Depends(get_session),
):
    query = select(Course)
    if status == "active":
        query = query.where(Course.archived_at.is_(None))
    elif status == "archived":
        query = query.where(Course.archived_at.is_not(None))
    courses = session.scalars(query.order_by(Course.code).limit(limit).offset(offset)).all()
    return CoursePage(items=[CourseRead.model_validate(course) for course in courses], limit=limit, offset=offset)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: UUID, session: Session = Depends(get_session)):
    course = session.get(Course, str(course_id))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def owned_course_for_update(course_id: UUID, principal: Principal, session: Session) -> Course:
    # Serialize edits and archival so an edit cannot race past archival.
    course = session.scalar(select(Course).where(Course.id == str(course_id)).with_for_update())
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.created_by != principal.subject:
        raise HTTPException(status_code=403, detail="Course author required")
    return course


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: UUID, payload: CourseUpdate,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    course = owned_course_for_update(course_id, principal, session)
    if course.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived courses cannot be edited")
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, name, value)
    commit_course(session, course)
    return course


@router.post("/{course_id}/archive", response_model=CourseRead)
def archive_course(
    course_id: UUID,
    principal: Principal = Depends(require_author), session: Session = Depends(get_session),
):
    course = owned_course_for_update(course_id, principal, session)
    if course.archived_at is None:
        course.archived_at = course.updated_at = utc_now()
        commit_course(session, course)
    return course
