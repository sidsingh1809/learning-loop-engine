"""Track A contracts. Observed bands remain internal fixtures until Day 10 state application."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.catalog_schemas import ActivityRead, Component, PolicyRead, StrictInput
from app.learner_schemas import TimestampRead
from datetime import datetime


class PlanCreate(StrictInput):
    enrollment_id: UUID
    target_skill_id: UUID
    learning_science_policy_id: UUID
    safety_policy_id: UUID
    time_budget_minutes: StrictInt = Field(gt=0, le=180)


class SkillSnapshot(StrictInput):
    id: str
    code: str
    title: str
    skill_kind: Literal["routine", "non_routine"]
    requires_automaticity: bool


class StateSnapshot(StrictInput):
    skill_id: str
    band: Literal["unknown", "developing", "secure"]
    evidence_count: StrictInt = Field(ge=0)
    revision: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def evidence_required(self):
        if self.band == "unknown":
            if self.evidence_count != 0 or self.revision != 0:
                raise ValueError("Unknown fixture states must have no evidence or revisions")
        elif self.evidence_count == 0 or self.revision == 0:
            raise ValueError("Observed fixture bands require evidence and a revision")
        return self


class PlannerInput(StrictInput):
    domain_version_id: str
    target_skill_id: str
    time_budget_minutes: StrictInt = Field(gt=0, le=180)
    skills: list[SkillSnapshot]
    edges: list[tuple[str, str]]
    states: list[StateSnapshot]
    learning_science_policy: PolicyRead
    safety_policy: PolicyRead
    activities: list[ActivityRead]


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    position: int
    role: Literal["whole_task_context", "focus_practice", "whole_task_return", "whole_task"]
    skill_id: UUID
    activity_variant_id: UUID
    components: list[Component]
    support_level: Literal["high", "minimal"]
    estimated_minutes: int
    rationale: str


class DecisionRead(BaseModel):
    planner_version: str
    input_fingerprint: str
    target_skill_id: UUID
    focus_skill_id: UUID
    context_key: str
    action: Literal["diagnostic_or_guided", "guided_practice", "independent_task"]
    support_level: Literal["high", "minimal"]
    complexity: Literal["introductory", "standard"]
    rationale: list[str]
    time_budget_minutes: int
    estimated_minutes: int
    unused_minutes: int
    completion_conditions: list[str]
    formal_certification: Literal[False]
    review_scope: Literal["synthetic_only"]
    steps: list[StepRead]


class PlanRead(TimestampRead):
    id: UUID
    enrollment_id: UUID
    domain_version_id: UUID
    learning_science_policy_id: UUID
    safety_policy_id: UUID
    created_at: datetime
    decision: DecisionRead
    input_snapshot: PlannerInput
