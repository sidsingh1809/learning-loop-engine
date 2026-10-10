from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

PATH = "/api/v1/learners/" + str(uuid4())
ENROLLMENT = PATH + "/enrollments/" + str(uuid4())
PAYLOAD = {"course_id": str(uuid4()), "domain_version_id": str(uuid4())}
OPERATIONS = [("POST", "/api/v1/learners", {}), ("GET", PATH, None),
              ("POST", PATH + "/enrollments", PAYLOAD), ("GET", PATH + "/enrollments", None),
              ("GET", ENROLLMENT, None), ("GET", ENROLLMENT + "/state", None)]


@pytest.mark.parametrize("method,path,payload", OPERATIONS)
def test_learner_routes_require_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["author", "instructor", "integration"])
def test_nonlearner_roles_denied_even_with_identity_headers(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in OPERATIONS:
        headers = {**role_headers[role], "X-Role": "learner", "X-Subject": "other-learner"}
        assert client.request(method, path, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize("payload", [{"id": str(uuid4())}, {"principal_subject": "victim"},
                                      {"email": "student@example.org"}, {"roles": ["learner"]}])
def test_registration_rejects_client_identity(client, role_headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post("/api/v1/learners", headers=role_headers["learner"], json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{}, {**PAYLOAD, "course_id": "bad"}, {**PAYLOAD, "domain_version_id": None},
                                      {**PAYLOAD, "learner_id": str(uuid4())}, {**PAYLOAD, "band": "secure"},
                                      {**PAYLOAD, "status": "active"}])
def test_enrollment_rejects_invalid_or_authoritative_fields(client, role_headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(PATH + "/enrollments", headers=role_headers["learner"], json=payload).status_code == 422


@pytest.mark.parametrize("missing", ["learners", "enrollments", "learner_skill_states"])
def test_readiness_requires_day5_schema(client, missing):
    class UnmigratedSession:
        def execute(self, statement):
            if "FROM " + missing + " " in str(statement):
                raise OperationalError("private SQL", {}, Exception("private connection"))
    app.dependency_overrides[get_session] = lambda: UnmigratedSession()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}


def test_openapi_has_learner_security_and_read_only_state(client):
    paths = client.get("/openapi.json").json()["paths"]
    learner_paths = {path: operations for path, operations in paths.items() if path.startswith("/api/v1/learners")}
    assert len(learner_paths) == 7
    for operations in learner_paths.values():
        for operation in operations.values():
            assert operation["security"] == [{"APIKeyHeader": []}]
    state = paths["/api/v1/learners/{learner_id}/enrollments/{enrollment_id}/state"]
    assert set(state) == {"get"}
