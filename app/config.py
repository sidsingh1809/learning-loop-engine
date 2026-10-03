from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.identity import DevelopmentCredential


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr
    api_key: SecretStr
    dev_principals: list[DevelopmentCredential] = Field(default_factory=list, repr=False)

    @model_validator(mode="after")
    def unique_development_credentials(self):
        keys = [self.api_key.get_secret_value()] + [p.api_key.get_secret_value() for p in self.dev_principals]
        subjects = ["dev-author"] + [p.subject for p in self.dev_principals]
        if len(set(keys)) != len(keys) or len(set(subjects)) != len(subjects):
            raise ValueError("Development credentials must have unique keys and subjects")
        return self

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("API_KEY must contain at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "mysql+pymysql":
            raise ValueError("DATABASE_URL must use mysql+pymysql")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
