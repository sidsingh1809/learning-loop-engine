"""Self-owned planning over authoritative enrollment state and reviewed catalogs."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalog import approved_policy
from app.catalog_schemas import ActivityRead, PolicyRead
from app.database import get_session
from app.domain_graph import load_graph
from app.identity import Principal
from app.learners import own_enrollment
from app.models import ActivityVariant, Course, DomainVersion, Enrollment, Learner, LearnerSkillState, LoopPlan, LoopStep
from app.planner import PlanningError, build_plan, canonical_snapshot
from app.planner_schemas import PlanCreate, PlanRead, PlannerInput, SkillSnapshot, StateSnapshot
from app.security import require_learner
from app.state_updates import apply_pending_scores

router = APIRouter(tags=["loop plans"], dependencies=[Depends(require_learner)],
                   responses={401: {"description": "Missing or invalid credentials"},
                              403: {"description": "Learner role required"},
                              404: {"description": "Resource not found or not accessible"},
                              409: {"description": "Unavailable graph, catalog or time budget"},
                              503: {"description": "Database operation unavailable"}})


def representation(plan, steps=None):
    return PlanRead(id=plan.id, enrollment_id=plan.enrollment_id, domain_version_id=plan.domain_version_id,
                    learning_science_policy_id=plan.learning_science_policy_id, safety_policy_id=plan.safety_policy_id,
                    created_at=plan.created_at, decision={**plan.decision, "steps": plan.steps if steps is None else steps}, input_snapshot=plan.input_snapshot)


@router.post("/learners/{learner_id}/loop-plans", response_model=PlanRead, status_code=201,
             responses={200: {"model": PlanRead, "description": "Existing identical input decision"}})
def create_plan(learner_id: UUID, payload: PlanCreate, response: Response,
                principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    enrollment = own_enrollment(learner_id, payload.enrollment_id, principal, session)
    # Serialize with archival/publication, then with same-enrollment planning.
    course = session.scalar(select(Course).where(Course.id == enrollment.course_id).with_for_update())
    domain = session.scalar(select(DomainVersion).where(DomainVersion.id == enrollment.domain_version_id).with_for_update())
    enrollment = session.scalar(select(Enrollment).where(Enrollment.id == enrollment.id).with_for_update())
    if course.archived_at is not None or domain.status != "published" or enrollment.status != "active":
        raise HTTPException(409, "Planning requires an active enrollment/course and published domain")
    # Historical Day 9 scores join the loop before taking the next input snapshot.
    applied_count = apply_pending_scores(enrollment, session)
    skills, edges = load_graph(domain.id, session)
    if str(payload.target_skill_id) not in {s.id for s in skills}:
        raise HTTPException(404, "Target skill not found in enrolled domain")
    learning = approved_policy(session, payload.learning_science_policy_id, "learning_science")
    safety = approved_policy(session, payload.safety_policy_id, "safety")
    activities = session.scalars(select(ActivityVariant).options(selectinload(ActivityVariant.mappings)).where(
        ActivityVariant.review_status == "approved", ActivityVariant.learning_science_policy_id == learning.id,
        ActivityVariant.safety_policy_id == safety.id)).all()
    states = session.scalars(select(LearnerSkillState).where(LearnerSkillState.enrollment_id == enrollment.id)
                             .order_by(LearnerSkillState.skill_id).with_for_update()).all()
    snapshot = PlannerInput(domain_version_id=domain.id, target_skill_id=str(payload.target_skill_id),
                            time_budget_minutes=payload.time_budget_minutes,
                            skills=[SkillSnapshot(**{name: getattr(s, name) for name in SkillSnapshot.model_fields}) for s in skills],
                            edges=[tuple(e) for e in edges],
                            states=[StateSnapshot(**{name: getattr(s, name) for name in StateSnapshot.model_fields}) for s in states],
                            learning_science_policy=PolicyRead.model_validate(learning), safety_policy=PolicyRead.model_validate(safety),
                            activities=[ActivityRead.model_validate(a) for a in activities])
    try:
        decision = build_plan(snapshot)
    except PlanningError as exc:
        raise HTTPException(409, str(exc)) from exc
    plan = session.scalar(select(LoopPlan).where(
        LoopPlan.enrollment_id == enrollment.id, LoopPlan.input_fingerprint == decision.input_fingerprint).with_for_update())
    if plan is not None:
        response.status_code = 200
        if applied_count:
            session.commit()
    else:
        plan = LoopPlan(enrollment_id=enrollment.id, domain_version_id=domain.id,
                        target_skill_id=str(decision.target_skill_id),
                        focus_skill_id=str(decision.focus_skill_id), learning_science_policy_id=learning.id,
                        safety_policy_id=safety.id, input_fingerprint=decision.input_fingerprint,
                        time_budget_minutes=decision.time_budget_minutes, estimated_minutes=decision.estimated_minutes,
                        input_snapshot=canonical_snapshot(snapshot), decision=decision.model_dump(mode="json", exclude={"steps"}),
                        steps=[LoopStep(domain_version_id=domain.id, **s.model_dump(mode="json")) for s in decision.steps])
        session.add(plan)
        session.commit()
        session.refresh(plan)
    response.headers["Location"] = "/api/v1/loop-plans/" + plan.id
    # Current reads are essential after waiting for another creator under MySQL repeatable-read.
    steps = session.scalars(select(LoopStep).where(LoopStep.loop_plan_id == plan.id)
                            .order_by(LoopStep.position).with_for_update()).all()
    return representation(plan, steps)


@router.get("/loop-plans/{plan_id}", response_model=PlanRead)
def get_plan(plan_id: UUID, principal: Principal = Depends(require_learner), session: Session = Depends(get_session)):
    plan = session.scalar(select(LoopPlan).join(Enrollment, Enrollment.id == LoopPlan.enrollment_id)
                          .join(Learner, Learner.id == Enrollment.learner_id).options(selectinload(LoopPlan.steps))
                          .where(LoopPlan.id == str(plan_id), Learner.principal_subject == principal.subject))
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return representation(plan)
