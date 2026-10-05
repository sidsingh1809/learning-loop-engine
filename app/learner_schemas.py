from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class LearnerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: UUID
    domain_version_id: UUID


class TimestampRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", check_fields=False)
    def utc_timestamp(self, value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class LearnerRead(TimestampRead):
    id: UUID
    created_at: datetime


class EnrollmentRead(TimestampRead):
    id: UUID
    learner_id: UUID
    course_id: UUID
    domain_version_id: UUID
    status: Literal["active"]
    created_at: datetime


class EnrollmentPage(BaseModel):
    items: list[EnrollmentRead]
    limit: int
    offset: int


class SkillStateRead(TimestampRead):
    skill_id: UUID
    domain_version_id: UUID
    band: Literal["unknown"]
    evidence_count: int
    revision: int
    updated_at: datetime


class LearnerStateRead(BaseModel):
    enrollment_id: UUID
    domain_version_id: UUID
    items: list[SkillStateRead]
    limit: int
    offset: int
