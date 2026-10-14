"""Read saved sequences across sessions without regenerating or resetting state."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities import generation_read, generation_rows, owned_plan, saved_sequence
from app.continuity_schemas import (CompletionCreate, CompletionRead, GenerationPage, PlanPage,
                                    ProgressRead, ReviewPage, ReviewRead)
from app.database import get_session
from app.generator import GenerationError
from app.identity import Principal
from app.learners import own_enrollment
from app.models import (Activity, ActivityCompletion, ActivityGeneration, Attempt, AttemptScore,
                        LearnerSkillState, LoopPlan, ReviewSchedule, utc_now)
from app.plans import representation
from app.security import require_learner
from app.state_updates import lock_enrollment

router = APIRouter(tags=["continuity"], dependencies=[Depends(require_learner)], responses={
    401: {"description": "Missing or invalid credentials"}, 403: {"description": "Learner role required"},
    404: {"description": "Resource not found or not accessible"},
    409: {"description": "Unavailable content or invalid completion"},
    503: {"description": "Database operation unavailable"}})


@router.get("/learners/{learner_id}/enrollments/{enrollment_id}/loop-plans", response_model=PlanPage)
def plan_history(learner_id: UUID, enrollment_id: UUID, limit: int = Query(20, ge=1, le=100),
                 offset: int = Query(0, ge=0), principal: Principal = Depends(require_learner),
                 session: Session = Depends(get_session)):
    enrollment = own_enrollment(learner_id, enrollment_id, principal, session)
    rows = session.scalars(select(LoopPlan).where(LoopPlan.enrollment_id == enrollment.id)
        .order_by(LoopPlan.created_at.desc(), LoopPlan.id.desc()).limit(limit).offset(offset)).all()
    return PlanPage(items=[representation(row) for row in rows], limit=limit, offset=offset)


@router.get("/loop-plans/{plan_id}/generations", response_model=GenerationPage)
def generation_history(plan_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                       principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    plan = owned_plan(plan_id, principal, session)
    rows = session.scalars(select(ActivityGeneration).where(ActivityGeneration.loop_plan_id == plan.id)
        .order_by(ActivityGeneration.created_at.desc(), ActivityGeneration.id.desc()).limit(limit).offset(offset)).all()
    return GenerationPage(items=[generation_read(row, generation_rows(row, session)) for row in rows], limit=limit, offset=offset)


@router.get("/activity-generations/{generation_id}/progress", response_model=ProgressRead)
def progress(generation_id: UUID, principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    generation = session.get(ActivityGeneration, str(generation_id))
    if generation is None:
        raise HTTPException(404, "Generation not found")
    plan = owned_plan(generation.loop_plan_id, principal, session)
    activities = generation_rows(generation, session)
    try:
        saved_sequence(generation, activities, representation(plan))
    except GenerationError as exc:
        raise HTTPException(409, str(exc)) from exc
    # All reads share one consistent DB snapshot. Attempts are never rewritten.
    attempts = session.execute(select(Attempt, AttemptScore.attempt_id).outerjoin(AttemptScore,
        AttemptScore.attempt_id == Attempt.id).join(Activity, Activity.id == Attempt.activity_id)
        .where(Activity.generation_id == generation.id).order_by(Attempt.created_at, Attempt.id)).all()
    completed = set(session.scalars(select(ActivityCompletion.activity_id).join(Activity)
        .where(Activity.generation_id == generation.id)).all())
    steps = []
    for activity in activities:
        submitted = [(a, scored) for a, scored in attempts if a.activity_id == activity.id]
        status = ("completed" if activity.id in completed or any(scored is not None for _, scored in submitted)
                  else "pending_review" if submitted else "not_started")
        steps.append(dict(activity_id=activity.id, position=activity.position, status=status,
                          attempt_ids=[a.id for a, _ in submitted]))
    next_step = next((step for step in steps if step["status"] != "completed"), None)
    status = ("awaiting_approval" if generation.review_status == "draft" else "rejected"
              if generation.review_status == "rejected" else "completed" if next_step is None
              else "pending_review" if next_step["status"] == "pending_review" else "in_progress")
    return ProgressRead(generation_id=generation.id, loop_plan_id=plan.id, status=status,
        next_activity_id=next_step["activity_id"] if next_step and generation.review_status == "approved" else None, steps=steps)


@router.post("/activities/{activity_id}/completion", response_model=CompletionRead, status_code=201,
             responses={200: {"model": CompletionRead, "description": "Existing support acknowledgment"}})
def complete_support(activity_id: UUID, payload: CompletionCreate, response: Response,
                     principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    activity = session.get(Activity, str(activity_id))
    if activity is None:
        raise HTTPException(404, "Activity not found")
    plan = owned_plan(activity.loop_plan_id, principal, session)
    course, _ = lock_enrollment(plan.enrollment_id, session)
    generation = session.scalar(select(ActivityGeneration).where(ActivityGeneration.id == activity.generation_id)
                                .with_for_update().execution_options(populate_existing=True))
    if generation.review_status != "approved":
        raise HTTPException(404, "Activity not found")
    from app.attempts import validated_step
    step = validated_step(activity, session)
    if step.rubric.scoring_method != "none":
        raise HTTPException(409, "Scored activities require an attempt, not a completion acknowledgment")
    completion = session.scalar(select(ActivityCompletion).where(ActivityCompletion.activity_id == activity.id).with_for_update())
    if completion is not None:
        response.status_code = 200
    else:
        if course.archived_at is not None:
            raise HTTPException(409, "New completion requires an active course")
        completion = ActivityCompletion(activity_id=activity.id)
        session.add(completion)
        session.commit()
        session.refresh(completion)
    return CompletionRead.model_validate(completion)


@router.get("/learners/{learner_id}/enrollments/{enrollment_id}/reviews", response_model=ReviewPage)
def reviews(learner_id: UUID, enrollment_id: UUID, due_only: bool = True, limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0), principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    enrollment = own_enrollment(learner_id, enrollment_id, principal, session)
    now = utc_now()
    query = select(ReviewSchedule, LearnerSkillState.band).join(LearnerSkillState,
        (LearnerSkillState.enrollment_id == ReviewSchedule.enrollment_id)
        & (LearnerSkillState.skill_id == ReviewSchedule.skill_id)).where(ReviewSchedule.enrollment_id == enrollment.id)
    if due_only:
        query = query.where(ReviewSchedule.due_at <= now)
    rows = session.execute(query.order_by(ReviewSchedule.due_at, ReviewSchedule.skill_id).limit(limit).offset(offset)).all()
    return ReviewPage(enrollment_id=enrollment.id, as_of=now, limit=limit, offset=offset,
        items=[ReviewRead(skill_id=row.skill_id, source_attempt_id=row.source_attempt_id, policy_version=row.policy_version,
                         scheduled_at=row.scheduled_at, due_at=row.due_at, due=row.due_at <= now, band=band) for row, band in rows])
