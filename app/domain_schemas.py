from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_serializer, field_validator, model_validator

CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
SkillKind = Literal["routine", "non_routine"]


class DomainVersionCreate(BaseModel):
    # Version number, ownership and lifecycle are server-controlled.
    model_config = ConfigDict(extra="forbid")


class CodedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=32, pattern=CODE_PATTERN)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class PatchInput(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def require_nonempty_nonnull_patch(cls, value):
        if isinstance(value, dict) and (not value or any(item is None for item in value.values())):
            raise ValueError("Provide at least one field; null values are not allowed")
        return value


class CompetencyCreate(CodedInput):
    statement: str = Field(min_length=1, max_length=10000)


class CompetencyUpdate(CompetencyCreate, PatchInput):
    code: Optional[str] = Field(default=None, min_length=1, max_length=32, pattern=CODE_PATTERN)
    statement: Optional[str] = Field(default=None, min_length=1, max_length=10000)


class SkillCreate(CodedInput):
    competency_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    skill_kind: SkillKind
    requires_automaticity: StrictBool = False

    @model_validator(mode="after")
    def automaticity_requires_routine(self):
        if self.skill_kind == "non_routine" and self.requires_automaticity:
            raise ValueError("Only routine skills can require automaticity")
        return self


class SkillUpdate(CodedInput, PatchInput):
    # Parent identifiers cannot be changed by PATCH.
    code: Optional[str] = Field(default=None, min_length=1, max_length=32, pattern=CODE_PATTERN)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    skill_kind: Optional[SkillKind] = None
    requires_automaticity: Optional[StrictBool] = None


class CreatedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime

    @field_serializer("created_at")
    def created_utc(self, value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class DomainVersionRead(CreatedRead):
    course_id: UUID
    version: int
    status: Literal["draft", "published"]
    published_at: Optional[datetime] = None

    @field_serializer("published_at")
    def published_utc(self, value: Optional[datetime]) -> Optional[str]:
        return None if value is None else value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class UpdatedRead(CreatedRead):
    updated_at: datetime

    @field_serializer("updated_at")
    def updated_utc(self, value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class CompetencyRead(UpdatedRead):
    domain_version_id: UUID
    code: str
    statement: str


class SkillRead(UpdatedRead):
    domain_version_id: UUID
    competency_id: UUID
    code: str
    title: str
    description: str
    skill_kind: SkillKind
    requires_automaticity: bool


class DomainVersionPage(BaseModel):
    items: list[DomainVersionRead]
    limit: int
    offset: int


class CompetencyPage(BaseModel):
    items: list[CompetencyRead]
    limit: int
    offset: int


class SkillPage(BaseModel):
    items: list[SkillRead]
    limit: int
    offset: int


class PrerequisiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # skill_id requires prerequisite_skill_id; arrows run prerequisite -> skill.
    skill_id: UUID
    prerequisite_skill_id: UUID

    @model_validator(mode="after")
    def reject_self_edge(self):
        if self.skill_id == self.prerequisite_skill_id:
            raise ValueError("A skill cannot require itself")
        return self


class PrerequisiteRead(CreatedRead):
    domain_version_id: UUID
    skill_id: UUID
    prerequisite_skill_id: UUID


class PrerequisitePage(BaseModel):
    items: list[PrerequisiteRead]
    limit: int
    offset: int


class DomainValidationIssue(BaseModel):
    code: str
    message: str
    resource_ids: list[UUID]


class DomainValidationRead(BaseModel):
    domain_version_id: UUID
    valid: bool
    issues: list[DomainValidationIssue]
    # Empty whenever validation fails. This order is structural, not a learning plan.
    topological_skill_ids: list[UUID]
