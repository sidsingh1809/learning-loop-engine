from datetime import datetime, timezone
from uuid import UUID
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class CourseUpdate(CourseCreate):
    """Omitted fields are preserved; supplied fields cannot be null."""

    code: Optional[str] = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)

    @model_validator(mode="before")
    @classmethod
    def require_nonempty_nonnull_patch(cls, value):
        if isinstance(value, dict) and (not value or any(item is None for item in value.values())):
            raise ValueError("Provide at least one field; null values are not allowed")
        return value


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    title: str
    description: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    archived_at: Optional[datetime]
    status: Literal["active", "archived"]

    @field_serializer("created_at", "updated_at", "archived_at")
    def utc_timestamp(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class CoursePage(BaseModel):
    items: list[CourseRead]
    limit: int
    offset: int
