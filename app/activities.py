"""Saved-plan generation, synthetic instructor review, and approved-only delivery."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_schemas import ReviewInput
from app.database import get_session
from app.generation_schemas import (DeliveredActivity, GenerationCreate,
                                    GenerationRead, ReviewContentRead)
from app.generator import GENERATOR_VERSION, TEMPLATE_VERSION, GenerationError, build_sequence, content_hash, learner_step, validate_output
from app.identity import Principal, Role
from app.models import Activity, ActivityGeneration, Course, Enrollment, Learner, LoopPlan, LoopStep, utc_now
from app.plans import representation
from app.security import require_api_key, require_learner

router = APIRouter(tags=["activities"], responses={401: {"description": "Missing or invalid credentials"},
    403: {"description": "Required role or review authority denied"}, 404: {"description": "Resource not found or not accessible"},
    409: {"description": "Unavailable template, invalid output or conflicting review"}, 503: {"description": "Database operation unavailable"}})


def require_instructor(principal: Principal = Depends(require_api_key)):
    if Role.instructor not in principal.roles:
        raise HTTPException(403, "Instructor role required")
    return principal


def owned_plan(plan_id, principal, session):
    plan = session.scalar(select(LoopPlan).join(Enrollment).join(Learner).where(
        LoopPlan.id == str(plan_id), Learner.principal_subject == principal.subject))
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan


def generation_rows(generation, session, lock=False):
    query = select(Activity).where(Activity.generation_id == generation.id).order_by(Activity.position)
    return session.scalars(query.with_for_update() if lock else query).all()


def generation_read(generation, rows):
    return GenerationRead(**{name: getattr(generation, name) for name in GenerationRead.model_fields if name != "activities"},
                          activities=[{"id": row.id, "position": row.position, "role": row.payload["role"],
                                       "activity_type": row.payload["content"]["activity_type"],
                                       "estimated_minutes": row.payload["estimated_minutes"]} for row in rows])


def saved_sequence(generation, rows, plan_read):
    candidate = {"generator_version": generation.generator_version, "template_version": generation.template_version,
                 "plan_fingerprint": plan_read.decision.input_fingerprint,
                 "learning_science_policy_id": plan_read.learning_science_policy_id,
                 "safety_policy_id": plan_read.safety_policy_id,
                 "estimated_minutes": plan_read.decision.estimated_minutes, "review_scope": generation.review_scope,
                 "steps": [r.payload for r in rows]}
    sequence = validate_output(candidate, plan_read.input_snapshot, plan_read.decision)
    if content_hash(sequence) != generation.content_hash:
        raise GenerationError("Stored content hash differs from validated sequence")
    return sequence


@router.post("/loop-plans/{plan_id}/generations", response_model=GenerationRead, status_code=201,
             responses={200: {"model": GenerationRead, "description": "Existing template generation"}})
def generate(plan_id: UUID, payload: GenerationCreate, response: Response,
             principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    plan = owned_plan(plan_id, principal, session)
    enrollment = session.get(Enrollment, plan.enrollment_id)
    course = session.scalar(select(Course).where(Course.id == enrollment.course_id).with_for_update())
    plan = session.scalar(select(LoopPlan).where(LoopPlan.id == plan.id).with_for_update())
    generation = session.scalar(select(ActivityGeneration).where(ActivityGeneration.loop_plan_id == plan.id,
                                ActivityGeneration.generator_version == GENERATOR_VERSION).with_for_update())
    if generation is not None:
        response.status_code = 200
    else:
        if course.archived_at is not None:
            raise HTTPException(409, "New generation requires an active course")
        steps = session.scalars(select(LoopStep).where(LoopStep.loop_plan_id == plan.id).order_by(LoopStep.position).with_for_update()).all()
        saved = representation(plan, steps)
        try:
            candidate = build_sequence(saved.input_snapshot, saved.decision)
            # A distinct boundary validates even a buggy/replaced adapter before persistence.
            candidate = validate_output(candidate, saved.input_snapshot, saved.decision)
        except GenerationError as exc:
            raise HTTPException(409, str(exc)) from exc
        generation = ActivityGeneration(loop_plan_id=plan.id, generator_version=GENERATOR_VERSION,
            template_version=TEMPLATE_VERSION, content_hash=content_hash(candidate), created_by=principal.subject,
            activities=[Activity(loop_plan_id=plan.id, position=s.position, payload=s.model_dump(mode="json")) for s in candidate.steps])
        session.add(generation)
        session.commit()
        session.refresh(generation)
    response.headers["Location"] = "/api/v1/activity-generations/" + generation.id
    return generation_read(generation, generation_rows(generation, session, lock=True))


@router.get("/activity-generations/{generation_id}", response_model=GenerationRead)
def get_generation(generation_id: UUID, principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    generation = session.get(ActivityGeneration, str(generation_id))
    if generation is None:
        raise HTTPException(404, "Generation not found")
    owned_plan(generation.loop_plan_id, principal, session)
    return generation_read(generation, generation_rows(generation, session))


@router.get("/activity-generations/{generation_id}/review-content", response_model=ReviewContentRead)
def review_content(generation_id: UUID, principal: Principal = Depends(require_instructor), session: Session = Depends(get_session)):
    generation = session.get(ActivityGeneration, str(generation_id))
    if generation is None:
        raise HTTPException(404, "Generation not found")
    rows = generation_rows(generation, session)
    plan = session.get(LoopPlan, generation.loop_plan_id)
    try:
        sequence = saved_sequence(generation, rows, representation(plan))
    except GenerationError as exc:
        raise HTTPException(409, str(exc)) from exc
    return ReviewContentRead(generation=generation_read(generation, rows), candidate=sequence)


@router.post("/activity-generations/{generation_id}/review", response_model=GenerationRead)
def review_generation(generation_id: UUID, payload: ReviewInput, principal: Principal = Depends(require_instructor),
                      session: Session = Depends(get_session)):
    generation = session.scalar(select(ActivityGeneration).where(ActivityGeneration.id == str(generation_id)).with_for_update())
    if generation is None:
        raise HTTPException(404, "Generation not found")
    if generation.created_by == principal.subject:
        raise HTTPException(403, "Review requires a different principal")
    rows = generation_rows(generation, session, lock=True)
    if generation.review_status != "draft":
        if (generation.review_status != payload.decision or generation.reviewed_by != principal.subject
                or generation.review_note != payload.note):
            raise HTTPException(409, "Generation already has a different review")
    else:
        plan = session.get(LoopPlan, generation.loop_plan_id)
        if payload.decision == "approved":
            try:
                saved_sequence(generation, rows, representation(plan))
            except GenerationError as exc:
                raise HTTPException(409, str(exc)) from exc
        generation.review_status = payload.decision
        generation.reviewed_by, generation.reviewed_at, generation.review_note = principal.subject, utc_now(), payload.note
        session.commit()
        session.refresh(generation)
    return generation_read(generation, rows)


@router.get("/activities/{activity_id}", response_model=DeliveredActivity)
def get_activity(activity_id: UUID, principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    row = session.get(Activity, str(activity_id))
    if row is None:
        raise HTTPException(404, "Activity not found")
    owned_plan(row.loop_plan_id, principal, session)
    generation = session.get(ActivityGeneration, row.generation_id)
    if generation.review_status != "approved":
        raise HTTPException(404, "Activity not found")
    plan = session.get(LoopPlan, row.loop_plan_id)
    try:
        sequence = saved_sequence(generation, generation_rows(generation, session), representation(plan))
    except GenerationError as exc:
        raise HTTPException(409, str(exc)) from exc
    step = next(s for s in sequence.steps if s.position == row.position)
    return DeliveredActivity(id=row.id, generation_id=row.generation_id, loop_plan_id=row.loop_plan_id,
                             step=learner_step(step), review_scope="synthetic_only", evidence_tier="provisional")
