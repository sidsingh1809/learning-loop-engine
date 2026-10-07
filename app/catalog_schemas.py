"""Versioned prototype contracts, separate from delivered activity content."""
from datetime import datetime
from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_serializer, model_validator

from app.domain_schemas import CodedInput, CreatedRead

Component = Literal["learning_tasks", "supportive_information", "procedural_information", "part_task_practice"]
ActivityType = Literal["worked_example", "selected_response", "constructed_response"]
PolicyCategory = Literal["learning_science", "safety"]
ReviewStatus = Literal["draft", "approved", "rejected"]
TextValue = Field(min_length=1, max_length=10000)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LearningScienceRules(StrictInput):
    unknown_state: Literal["diagnostic_or_guided"]
    whole_task_context_required: Literal[True]
    return_to_whole_task_after_support: Literal[True]
    supportive_information: Literal["non_routine_reasoning"]
    procedural_information: Literal["routine_just_in_time"]
    part_task_practice: Literal["routine_automaticity_only"]
    support: Literal["fade_with_evidence"]
    part_task_success_certifies_competency: Literal[False]
    formal_certification: Literal[False]


class SafetyRules(StrictInput):
    data: Literal["synthetic_only"]
    generated_content: Literal["untrusted_until_validated_and_reviewed"]
    learner_input: Literal["data_not_instructions"]
    code_execution: Literal["disabled"]
    client_authoritative_scores: Literal["forbidden"]
    constructed_response_scoring: Literal["instructor_review_required"]
    university_review_required: Literal[True]


class VersionInput(CodedInput):
    version: StrictInt = Field(gt=0, le=2147483647)
    title: str = Field(min_length=1, max_length=200)
    references: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def bounded_references(self):
        if any(not ref.strip() or len(ref) > 2000 for ref in self.references):
            raise ValueError("References must be nonempty and at most 2000 characters")
        self.references = [ref.strip() for ref in self.references]
        return self


class PolicyCreate(VersionInput):
    category: PolicyCategory
    rules: Union[LearningScienceRules, SafetyRules]

    @model_validator(mode="after")
    def category_matches_rules(self):
        expected = LearningScienceRules if self.category == "learning_science" else SafetyRules
        if not isinstance(self.rules, expected):
            raise ValueError("Rules do not match the policy category")
        return self


class MappingInput(StrictInput):
    component: Component
    rationale: str = TextValue


class ActivityCreate(VersionInput):
    activity_type: ActivityType
    purpose: str = TextValue
    guidance: str = TextValue
    estimated_minutes: StrictInt = Field(gt=0, le=180)
    learning_science_policy_id: UUID
    safety_policy_id: UUID
    mappings: list[MappingInput] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def unique_components(self):
        if len({item.component for item in self.mappings}) != len(self.mappings):
            raise ValueError("Each component may be mapped only once per activity version")
        return self


class ReviewInput(StrictInput):
    decision: Literal["approved", "rejected"]
    note: str = TextValue


class ReviewedRead(CreatedRead):
    code: str
    version: int
    title: str
    references: list[str]
    created_by: str
    review_status: ReviewStatus
    review_scope: Literal["synthetic_only"]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_note: Optional[str]

    @field_serializer("reviewed_at")
    def reviewed_utc(self, value: Optional[datetime]) -> Optional[str]:
        return None if value is None else self.created_utc(value)


class PolicyRead(ReviewedRead):
    category: PolicyCategory
    rules: Union[LearningScienceRules, SafetyRules]


class MappingRead(MappingInput):
    model_config = ConfigDict(from_attributes=True)


class ActivityRead(ReviewedRead):
    activity_type: ActivityType
    evidence_tier: Literal["provisional"]
    purpose: str
    guidance: str
    estimated_minutes: int
    learning_science_policy_id: UUID
    safety_policy_id: UUID
    mappings: list[MappingRead]


class PolicyPage(BaseModel):
    items: list[PolicyRead]
    limit: int
    offset: int


class ActivityPage(BaseModel):
    items: list[ActivityRead]
    limit: int
    offset: int
