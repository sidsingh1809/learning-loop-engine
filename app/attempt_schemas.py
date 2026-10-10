"""Learners submit answers; only server scorers and instructors create evidence."""
from datetime import datetime
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import Field, StrictInt

from app.catalog_schemas import StrictInput, TextValue
from app.generation_schemas import GeneratedStep
from app.learner_schemas import TimestampRead


class SelectedAnswer(StrictInput):
    activity_type: Literal["selected_response"]
    choice_id: str = Field(min_length=1, max_length=32)


class WrittenAnswer(StrictInput):
    activity_type: Literal["constructed_response"]
    text: str = TextValue


Answer = Annotated[Union[SelectedAnswer, WrittenAnswer], Field(discriminator="activity_type")]


class AttemptCreate(StrictInput):
    idempotency_key: UUID
    response: Answer


class CriterionScore(StrictInput):
    code: str = Field(min_length=1, max_length=32)
    points: StrictInt = Field(ge=0, le=100)


class AttemptReview(StrictInput):
    criteria: list[CriterionScore] = Field(min_length=1, max_length=10)
    note: str = TextValue


class EvidenceRead(StrictInput):
    attempt_id: UUID
    criterion_code: str
    domain_version_id: UUID
    skill_id: UUID
    points: int
    max_points: int
    evidence_kind: Literal["part_task", "whole_task"]
    evidence_tier: Literal["provisional"]
    formal_certification: Literal[False]


class ScoreRead(TimestampRead):
    scoring_method: Literal["selected_response", "instructor_review"]
    scorer_version: str
    rubric_version: str
    review_scope: Literal["synthetic_only"]
    reviewed_by: Optional[str]
    review_note: Optional[str]
    created_at: datetime
    evidence: list[EvidenceRead]


class StateValues(StrictInput):
    band: Literal["unknown", "developing", "secure"]
    evidence_count: int
    revision: int
    whole_task_evidence_count: int
    part_task_evidence_count: int
    whole_task_attempt_count: int
    whole_task_points: int
    whole_task_max_points: int
    policy_version: Optional[str]


class StateChange(StrictInput):
    skill_id: UUID
    criterion_codes: list[str]
    before: StateValues
    after: StateValues


class StateApplicationRead(TimestampRead):
    attempt_id: UUID
    enrollment_id: UUID
    domain_version_id: UUID
    policy_version: str
    changes: list[StateChange]
    formal_certification: Literal[False]
    created_at: datetime


class AttemptRead(TimestampRead):
    id: UUID
    activity_id: UUID
    loop_plan_id: UUID
    enrollment_id: UUID
    domain_version_id: UUID
    idempotency_key: UUID
    response: Answer
    scoring_method: Literal["selected_response", "instructor_review"]
    created_at: datetime
    status: Literal["pending_review", "scored"]
    score: Optional[ScoreRead]
    state_application: Optional[StateApplicationRead]


class AttemptPage(StrictInput):
    items: list[AttemptRead]
    limit: int
    offset: int


class AttemptReviewContent(StrictInput):
    attempt: AttemptRead
    step: GeneratedStep
