"""Identity shared by development authentication and future university adapters."""
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Role(str, Enum):
    author = "author"
    instructor = "instructor"
    learner = "learner"
    integration = "integration"


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[Role]


class DevelopmentCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    roles: frozenset[Role] = Field(min_length=1)
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("Development API keys must contain at least 32 characters")
        return value
