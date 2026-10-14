"""A versioned experimental reminder, separate from mastery and planner replay."""
from datetime import timedelta

from sqlalchemy import select

from app.models import ReviewSchedule

REVIEW_POLICY_VERSION = "experimental-review-v1"
REVIEW_INTERVAL = timedelta(days=7)


def schedule_whole_task_review(attempt, score, evidence, session):
    """Caller holds enrollment lock. Anchor to score time, never retry/read time."""
    for skill_id in sorted({e.skill_id for e in evidence if e.evidence_kind == "whole_task"}):
        row = session.scalar(select(ReviewSchedule).where(
            ReviewSchedule.enrollment_id == attempt.enrollment_id,
            ReviewSchedule.skill_id == skill_id).with_for_update())
        if row is not None and (row.scheduled_at, row.source_attempt_id) >= (score.created_at, attempt.id):
            continue
        if row is None:
            row = ReviewSchedule(enrollment_id=attempt.enrollment_id, skill_id=skill_id,
                                 domain_version_id=attempt.domain_version_id)
            session.add(row)
        row.source_attempt_id = attempt.id
        row.policy_version = REVIEW_POLICY_VERSION
        row.scheduled_at = score.created_at
        row.due_at = score.created_at + REVIEW_INTERVAL
