"""Learner-owned continuity and experimental review contracts."""
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_serializer

from app.catalog_schemas import StrictInput
from app.generation_schemas import GenerationRead
from app.learner_schemas import TimestampRead
from app.planner_schemas import PlanRead


class CompletionCreate(StrictInput):
    pass


class CompletionRead(TimestampRead):
    activity_id: UUID
    created_at: datetime


class ProgressStep(BaseModel):
    activity_id: UUID
    position: int
    status: Literal["not_started", "pending_review", "completed"]
    attempt_ids: list[UUID]


class ProgressRead(BaseModel):
    generation_id: UUID
    loop_plan_id: UUID
    status: Literal["awaiting_approval", "rejected", "in_progress", "pending_review", "completed"]
    next_activity_id: Optional[UUID]
    steps: list[ProgressStep]


class GenerationPage(BaseModel):
    items: list[GenerationRead]
    limit: int
    offset: int


class PlanPage(BaseModel):
    items: list[PlanRead]
    limit: int
    offset: int


class ReviewRead(BaseModel):
    skill_id: UUID
    source_attempt_id: UUID
    policy_version: Literal["experimental-review-v1"]
    scheduled_at: datetime
    due_at: datetime
    due: bool
    band: Literal["unknown", "developing", "secure"]
    action: Literal["whole_task_review"] = "whole_task_review"
    rationale: str = "Experimental seven-day reminder after whole-task scoring; no mastery decay or reset is inferred."
    formal_certification: Literal[False] = False

    @field_serializer("scheduled_at", "due_at")
    def utc_timestamp(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class ReviewPage(BaseModel):
    enrollment_id: UUID
    as_of: datetime
    items: list[ReviewRead]
    limit: int
    offset: int

    @field_serializer("as_of")
    def utc_timestamp(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
