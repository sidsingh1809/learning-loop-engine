"""Apply terminal scores exactly once inside the caller's enrollment transaction."""
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Attempt, AttemptScore, Course, Enrollment, Evidence, LearnerSkillState, StateApplication, utc_now
from app.state_policy import STATE_FIELDS, STATE_POLICY_VERSION, advance_state


def lock_enrollment(enrollment_id, session):
    enrollment = session.get(Enrollment, enrollment_id)
    course = session.scalar(select(Course).where(Course.id == enrollment.course_id).with_for_update()
                            .execution_options(populate_existing=True))
    enrollment = session.scalar(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update()
                                .execution_options(populate_existing=True))
    return course, enrollment


def apply_pending_scores(enrollment, session):
    """Caller holds course then enrollment locks; never commit independently.

    Current locking reads are required after ownership reads under MySQL's
    repeatable-read isolation. Historical Day 9 evidence is applied unchanged.
    """
    session.flush()
    attempts = session.scalars(select(Attempt).join(AttemptScore, AttemptScore.attempt_id == Attempt.id)
        .where(Attempt.enrollment_id == enrollment.id)
        .order_by(AttemptScore.created_at, Attempt.id).with_for_update()).all()
    applied = 0
    for attempt in attempts:
        existing = session.scalar(select(StateApplication).where(StateApplication.attempt_id == attempt.id).with_for_update())
        if existing is not None:
            continue
        rows = session.scalars(select(Evidence).where(Evidence.attempt_id == attempt.id)
                               .order_by(Evidence.criterion_code).with_for_update()).all()
        if not rows:
            raise HTTPException(409, "Scored attempt has no evidence to apply")
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.skill_id].append(row)
        changes = []
        for skill_id in sorted(grouped):
            state = session.scalar(select(LearnerSkillState).where(
                LearnerSkillState.enrollment_id == enrollment.id, LearnerSkillState.skill_id == skill_id,
                LearnerSkillState.domain_version_id == attempt.domain_version_id).with_for_update()
                .execution_options(populate_existing=True))
            if state is None:
                raise HTTPException(409, "Evidence has no matching enrolled skill state")
            before = {name: getattr(state, name) for name in STATE_FIELDS}
            after = advance_state(before, grouped[skill_id])
            for name, value in after.items():
                setattr(state, name, value)
            state.updated_at = utc_now()
            changes.append({"skill_id": skill_id, "criterion_codes": [e.criterion_code for e in grouped[skill_id]],
                            "before": before, "after": after})
        session.add(StateApplication(attempt_id=attempt.id, enrollment_id=enrollment.id,
            domain_version_id=attempt.domain_version_id, policy_version=STATE_POLICY_VERSION, changes=changes))
        session.flush()
        applied += 1
    return applied
