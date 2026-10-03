import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database import get_session
from app.main import app
from app.schemas import CourseCreate


def test_liveness_does_not_require_database(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("key", [None, "wrong", "é" * 32])
def test_course_api_rejects_missing_or_invalid_credentials(client, key):
    # Non-ASCII credential comparison is separately checked at function level.
    if key is not None and not key.isascii():
        from app.security import require_api_key
        from app.config import get_settings
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:
            require_api_key(key, get_settings())
        assert error.value.status_code == 401
        return
    headers = {} if key is None else {"X-API-Key": key}
    assert client.get("/api/v1/courses", headers=headers).status_code == 401


@pytest.mark.parametrize("payload", [
    {"code": "bad code", "title": "Valid"},
    {"code": "CS101", "title": "   "},
    {"code": "CS101", "title": "Valid", "unexpected": "value"},
    {"code": "CS101", "title": "Valid", "description": "x" * 10001},
])
def test_invalid_course_payloads(client, headers, payload):
    # Override the DB dependency so malformed requests cannot depend on database uptime.
    app.dependency_overrides[get_session] = lambda: None
    assert client.post("/api/v1/courses", headers=headers, json=payload).status_code == 422


def test_schema_normalizes_course_code():
    course = CourseCreate(code=" cs101 ", title=" Intro ")
    assert course.code == "CS101"
    assert course.title == "Intro"


def test_readiness_hides_database_details(client):
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("secret SQL", {}, Exception("secret password"))
    app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}
    assert "secret" not in response.text


def test_configuration_requires_mysql_and_long_key():
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///demo.db", api_key="x" * 32, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(database_url="mysql+pymysql://x:x@localhost/x", api_key="short", _env_file=None)


def test_openapi_documents_auth_and_versioned_routes(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/courses"]["post"]
    assert operation["security"] == [{"APIKeyHeader": []}]
    assert "201" in operation["responses"]
    assert "patch" in schema["paths"]["/api/v1/courses/{course_id}"]
    assert "delete" not in schema["paths"]["/api/v1/courses/{course_id}"]
    assert "post" in schema["paths"]["/api/v1/courses/{course_id}/archive"]


@pytest.mark.parametrize("payload", [
    {}, {"title": None}, {"code": None}, {"description": None}, {"title": " "},
    {"code": "bad code"}, {"description": "x" * 10001}, {"status": "archived"},
    {"created_by": "other-author"}, {"archived_at": "2026-10-01T00:00:00Z"},
])
def test_invalid_patches(client, headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    response = client.patch("/api/v1/courses/00000000-0000-0000-0000-000000000001", headers=headers, json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("role", ["learner", "instructor", "integration"])
@pytest.mark.parametrize("method,suffix,payload", [
    ("POST", "", {"code": "CS101", "title": "Test"}),
    ("PATCH", "/00000000-0000-0000-0000-000000000001", {"title": "Changed"}),
    ("POST", "/00000000-0000-0000-0000-000000000001/archive", None),
])
def test_read_only_roles_cannot_write_or_spoof_author(client, role_headers, role, method, suffix, payload):
    app.dependency_overrides[get_session] = lambda: None
    headers = {**role_headers[role], "X-Role": "author", "X-Subject": "dev-author"}
    assert client.request(method, "/api/v1/courses" + suffix, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize("entry", [
    {"subject": "dev-author", "roles": ["learner"], "api_key": "y" * 32},
    {"subject": "someone", "roles": ["learner"], "api_key": "x" * 32},
    {"subject": "someone", "roles": ["admin"], "api_key": "y" * 32},
    {"subject": "someone", "roles": [], "api_key": "y" * 32},
    {"subject": "someone", "roles": ["author"], "api_key": "short"},
])
def test_development_principals_fail_closed_on_bad_config(entry):
    with pytest.raises(ValidationError):
        Settings(database_url="mysql+pymysql://x:x@localhost/x", api_key="x" * 32, dev_principals=[entry], _env_file=None)
