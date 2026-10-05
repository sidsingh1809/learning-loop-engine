import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings
from app.identity import Principal, Role


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    key: Optional[str] = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> Principal:
    credentials = [(settings.api_key, Principal("dev-author", frozenset({Role.author})))]
    credentials.extend((entry.api_key, Principal(entry.subject, entry.roles)) for entry in settings.dev_principals)
    matched = None
    if key is not None:
        for expected, principal in credentials:
            if secrets.compare_digest(key.encode("utf-8"), expected.get_secret_value().encode("utf-8")):
                matched = principal
    if matched is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return matched


def require_author(principal: Principal = Depends(require_api_key)) -> Principal:
    if Role.author not in principal.roles:
        raise HTTPException(status_code=403, detail="Author role required")
    return principal


def require_learner(principal: Principal = Depends(require_api_key)) -> Principal:
    if Role.learner not in principal.roles:
        raise HTTPException(status_code=403, detail="Learner role required")
    return principal
