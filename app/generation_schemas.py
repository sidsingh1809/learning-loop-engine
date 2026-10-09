"""Validated Track B payloads; scoring keys stay in instructor-only candidates."""
from datetime import datetime
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import Field, StrictInt, field_serializer, model_validator

from app.catalog_schemas import ActivityType, Component, ReviewStatus, StrictInput, TextValue
from app.learner_schemas import TimestampRead


class GenerationCreate(StrictInput):
    pass


class Choice(StrictInput):
    id: str = Field(min_length=1, max_length=32)
    text: str = TextValue


class WorkedExample(StrictInput):
    activity_type: Literal["worked_example"]
    prompt: str = TextValue
    code: str = TextValue
    explanation: str = TextValue
    supportive_information: Optional[str] = TextValue
    procedural_information: Optional[str] = TextValue


class SelectedResponse(StrictInput):
    activity_type: Literal["selected_response"]
    prompt: str = TextValue
    choices: list[Choice] = Field(min_length=2, max_length=6)
    correct_choice_id: str = Field(min_length=1, max_length=32)
    explanation: str = TextValue

    @model_validator(mode="after")
    def valid_key(self):
        ids = [c.id for c in self.choices]
        if len(set(ids)) != len(ids) or self.correct_choice_id not in ids:
            raise ValueError("Choices must be unique and contain exactly one keyed answer")
        return self


class ConstructedResponse(StrictInput):
    activity_type: Literal["constructed_response"]
    prompt: str = TextValue
    code: str = TextValue
    response_instructions: str = TextValue


Content = Annotated[Union[WorkedExample, SelectedResponse, ConstructedResponse], Field(discriminator="activity_type")]


class Criterion(StrictInput):
    code: str = Field(min_length=1, max_length=32)
    skill_id: UUID
    description: str = TextValue
    max_points: StrictInt = Field(gt=0, le=100)
    expected_response: str = TextValue


class Rubric(StrictInput):
    version: Literal["synthetic-rubric-v1"]
    scoring_method: Literal["none", "selected_response", "instructor_review"]
    criteria: list[Criterion] = Field(max_length=10)
    max_points: StrictInt = Field(ge=0, le=1000)
    formal_certification: Literal[False]

    @model_validator(mode="after")
    def consistent_points(self):
        if len({c.code for c in self.criteria}) != len(self.criteria):
            raise ValueError("Rubric criterion codes must be unique")
        if self.max_points != sum(c.max_points for c in self.criteria):
            raise ValueError("Rubric total must equal criterion points")
        if (self.scoring_method == "none") != (not self.criteria):
            raise ValueError("Only unscored content may have an empty rubric")
        return self


class GeneratedStep(StrictInput):
    position: StrictInt = Field(gt=0)
    role: Literal["whole_task_context", "focus_practice", "whole_task_return", "whole_task"]
    skill_id: UUID
    target_skill_id: UUID
    focus_skill_id: UUID
    activity_variant_id: UUID
    components: list[Component] = Field(min_length=1, max_length=4)
    support_level: Literal["high", "minimal"]
    estimated_minutes: StrictInt = Field(gt=0, le=180)
    context_key: str = Field(min_length=1, max_length=200)
    scenario_id: Literal["positive-sales-v1"]
    content: Content
    rubric: Rubric

    @model_validator(mode="after")
    def format_matches_rubric(self):
        scoring = {"worked_example": "none", "selected_response": "selected_response",
                   "constructed_response": "instructor_review"}[self.content.activity_type]
        if self.rubric.scoring_method != scoring:
            raise ValueError("Scoring method must match activity format")
        return self


class GeneratedSequence(StrictInput):
    generator_version: Literal["track-b-template-v1"]
    template_version: Literal["positive-sales-v1"]
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    learning_science_policy_id: UUID
    safety_policy_id: UUID
    estimated_minutes: StrictInt = Field(gt=0, le=180)
    review_scope: Literal["synthetic_only"]
    steps: list[GeneratedStep] = Field(min_length=1, max_length=3)


class ActivitySummary(StrictInput):
    id: UUID
    position: int
    role: str
    activity_type: ActivityType
    estimated_minutes: int


class GenerationRead(TimestampRead):
    id: UUID
    loop_plan_id: UUID
    generator_version: str
    template_version: str
    content_hash: str
    review_status: ReviewStatus
    review_scope: Literal["synthetic_only"]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_note: Optional[str]
    created_at: datetime
    activities: list[ActivitySummary]

    @field_serializer("reviewed_at")
    def reviewed_utc(self, value: Optional[datetime]) -> Optional[str]:
        return None if value is None else self.utc_timestamp(value)


class ReviewContentRead(StrictInput):
    generation: GenerationRead
    candidate: GeneratedSequence


class PublicSelectedResponse(StrictInput):
    activity_type: Literal["selected_response"]
    prompt: str = TextValue
    choices: list[Choice] = Field(min_length=2, max_length=6)


class PublicCriterion(StrictInput):
    code: str = Field(min_length=1, max_length=32)
    skill_id: UUID
    description: str = TextValue
    max_points: StrictInt = Field(gt=0, le=100)


class PublicRubric(Rubric):
    criteria: list[PublicCriterion] = Field(max_length=10)


class DeliveredStep(GeneratedStep):
    content: Annotated[Union[WorkedExample, PublicSelectedResponse, ConstructedResponse], Field(discriminator="activity_type")]
    rubric: PublicRubric


class DeliveredActivity(StrictInput):
    id: UUID
    generation_id: UUID
    loop_plan_id: UUID
    step: DeliveredStep
    review_scope: Literal["synthetic_only"]
    evidence_tier: Literal["provisional"]
