"""Append-only answers and scores; learner state application belongs to Day 10."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities import generation_rows, owned_plan, require_instructor, saved_sequence
from app.attempt_schemas import (AttemptCreate, AttemptPage, AttemptRead, AttemptReview,
                                 AttemptReviewContent, EvidenceRead, ScoreRead)
from app.database import get_session
from app.generator import GenerationError
from app.identity import Principal
from app.models import Activity, ActivityGeneration, Attempt, AttemptScore, Course, Enrollment, Evidence, Learner, LoopPlan
from app.plans import representation
from app.scoring import INSTRUCTOR_SCORER, SELECTED_SCORER, ScoringError, request_hash, reviewed_points, selected_points, validate_answer
from app.security import require_learner

router = APIRouter(tags=["attempts"], responses={401: {"description": "Missing or invalid credentials"},
    403: {"description": "Required role or review authority denied"}, 404: {"description": "Resource not found or not accessible"},
    409: {"description": "Conflicting retry, terminal score, or unavailable activity"},
    503: {"description": "Database operation unavailable"}})


def score_rows(attempt, session, lock=False):
    score_query = select(AttemptScore).where(AttemptScore.attempt_id == attempt.id)
    evidence_query = select(Evidence).where(Evidence.attempt_id == attempt.id).order_by(Evidence.criterion_code)
    if lock:
        score_query, evidence_query = score_query.with_for_update(), evidence_query.with_for_update()
    return session.scalar(score_query), session.scalars(evidence_query).all()


def attempt_read(attempt, session, lock=False):
    score, evidence = score_rows(attempt, session, lock)
    result = None if score is None else ScoreRead(
        **{name: getattr(score, name) for name in ScoreRead.model_fields if name != "evidence"},
        evidence=[EvidenceRead.model_validate(row, from_attributes=True) for row in evidence])
    return AttemptRead(**{name: getattr(attempt, name) for name in AttemptRead.model_fields if name not in {"status", "score"}},
                       status="pending_review" if score is None else "scored", score=result)


def owned_attempt(attempt_id, principal, session):
    row = session.scalar(select(Attempt).join(Enrollment, Attempt.enrollment_id == Enrollment.id).join(Learner).where(
        Attempt.id == str(attempt_id), Learner.principal_subject == principal.subject))
    if row is None:
        raise HTTPException(404, "Attempt not found")
    return row


def validated_step(activity, session):
    generation = session.get(ActivityGeneration, activity.generation_id)
    if generation.review_status != "approved":
        raise HTTPException(404, "Activity not found")
    plan = session.get(LoopPlan, activity.loop_plan_id)
    try:
        sequence = saved_sequence(generation, generation_rows(generation, session), representation(plan))
    except GenerationError as exc:
        raise HTTPException(409, str(exc)) from exc
    return next(s for s in sequence.steps if s.position == activity.position)


def append_score(attempt, step, points, session, reviewer=None, note=None):
    score = AttemptScore(attempt_id=attempt.id, scoring_method=attempt.scoring_method,
                         scorer_version=SELECTED_SCORER if reviewer is None else INSTRUCTOR_SCORER,
                         rubric_version=step.rubric.version, reviewed_by=reviewer, review_note=note)
    session.add(score)
    session.flush()
    for criterion in step.rubric.criteria:
        session.add(Evidence(attempt_id=attempt.id, criterion_code=criterion.code,
            domain_version_id=attempt.domain_version_id, skill_id=str(criterion.skill_id),
            points=points[criterion.code], max_points=criterion.max_points,
            evidence_kind="part_task" if step.role == "focus_practice" else "whole_task"))


@router.post("/activities/{activity_id}/attempts", response_model=AttemptRead, status_code=201,
             responses={200: {"model": AttemptRead, "description": "Existing attempt for this key and answer"}})
def submit_attempt(activity_id: UUID, payload: AttemptCreate, response: Response,
                   principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    activity = session.get(Activity, str(activity_id))
    if activity is None:
        raise HTTPException(404, "Activity not found")
    plan = owned_plan(activity.loop_plan_id, principal, session)
    enrollment = session.get(Enrollment, plan.enrollment_id)
    # Serialize new submissions with course archival and other enrollment writes.
    course = session.scalar(select(Course).where(Course.id == enrollment.course_id).with_for_update())
    session.scalar(select(Enrollment).where(Enrollment.id == enrollment.id).with_for_update())
    plan = session.scalar(select(LoopPlan).where(LoopPlan.id == plan.id).with_for_update())
    generation = session.scalar(select(ActivityGeneration).where(ActivityGeneration.id == activity.generation_id)
                                .with_for_update().execution_options(populate_existing=True))
    if generation.review_status != "approved":
        raise HTTPException(404, "Activity not found")
    fingerprint = request_hash(activity.id, payload.response)
    attempt = session.scalar(select(Attempt).where(Attempt.enrollment_id == enrollment.id,
        Attempt.idempotency_key == str(payload.idempotency_key)).with_for_update())
    if attempt is not None:
        if attempt.request_hash != fingerprint:
            raise HTTPException(409, "Idempotency key already used for a different activity or response")
        response.status_code = 200
    else:
        if course.archived_at is not None:
            raise HTTPException(409, "New attempts require an active course")
        step = validated_step(activity, session)
        try:
            validate_answer(step, payload.response)
        except ScoringError as exc:
            raise HTTPException(409 if step.content.activity_type == "worked_example" else 422, str(exc)) from exc
        attempt = Attempt(activity_id=activity.id, loop_plan_id=plan.id, enrollment_id=enrollment.id,
            domain_version_id=plan.domain_version_id, idempotency_key=str(payload.idempotency_key),
            request_hash=fingerprint, response=payload.response.model_dump(mode="json"),
            scoring_method=step.rubric.scoring_method, submitted_by=principal.subject)
        session.add(attempt)
        session.flush()
        if attempt.scoring_method == "selected_response":
            append_score(attempt, step, selected_points(step, payload.response), session)
        session.commit()
        session.refresh(attempt)
    response.headers["Location"] = "/api/v1/attempts/" + attempt.id
    return attempt_read(attempt, session, lock=True)


@router.get("/activities/{activity_id}/attempts", response_model=AttemptPage)
def list_attempts(activity_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    activity = session.get(Activity, str(activity_id))
    if activity is None:
        raise HTTPException(404, "Activity not found")
    owned_plan(activity.loop_plan_id, principal, session)
    if session.get(ActivityGeneration, activity.generation_id).review_status != "approved":
        raise HTTPException(404, "Activity not found")
    rows = session.scalars(select(Attempt).where(Attempt.activity_id == activity.id)
                           .order_by(Attempt.created_at, Attempt.id).limit(limit).offset(offset)).all()
    return AttemptPage(items=[attempt_read(a, session) for a in rows], limit=limit, offset=offset)


@router.get("/attempts/{attempt_id}", response_model=AttemptRead)
def get_attempt(attempt_id: UUID, principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    return attempt_read(owned_attempt(attempt_id, principal, session), session)


def instructor_attempt(attempt_id, principal, session, lock=False):
    query = select(Attempt).where(Attempt.id == str(attempt_id))
    attempt = session.scalar(query.with_for_update() if lock else query)
    if attempt is None:
        raise HTTPException(404, "Attempt not found")
    if attempt.submitted_by == principal.subject:
        raise HTTPException(403, "Review requires a different principal")
    if attempt.scoring_method != "instructor_review":
        raise HTTPException(409, "Only constructed responses accept instructor review")
    return attempt


@router.get("/attempts/{attempt_id}/review-content", response_model=AttemptReviewContent)
def review_content(attempt_id: UUID, principal: Principal = Depends(require_instructor), session: Session = Depends(get_session)):
    attempt = instructor_attempt(attempt_id, principal, session)
    step = validated_step(session.get(Activity, attempt.activity_id), session)
    return AttemptReviewContent(attempt=attempt_read(attempt, session), step=step)


@router.post("/attempts/{attempt_id}/review", response_model=AttemptRead)
def review_attempt(attempt_id: UUID, payload: AttemptReview, principal: Principal = Depends(require_instructor),
                   session: Session = Depends(get_session)):
    attempt = instructor_attempt(attempt_id, principal, session, lock=True)
    step = validated_step(session.get(Activity, attempt.activity_id), session)
    try:
        points = reviewed_points(step, payload)
    except ScoringError as exc:
        raise HTTPException(422, str(exc)) from exc
    score, evidence = score_rows(attempt, session, lock=True)
    if score is not None:
        if (score.reviewed_by != principal.subject or score.review_note != payload.note
                or {e.criterion_code: e.points for e in evidence} != points):
            raise HTTPException(409, "Attempt already has a different terminal score")
    else:
        append_score(attempt, step, points, session, principal.subject, payload.note)
        session.commit()
    return attempt_read(attempt, session, lock=True)
