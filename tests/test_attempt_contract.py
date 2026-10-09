from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

ACT = "/api/v1/activities/" + str(uuid4()) + "/attempts"
ATT = "/api/v1/attempts/" + str(uuid4())
PAYLOAD = {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "a"}}
REVIEW = {"criteria": [{"code": "FOCUS", "points": 1}], "note": "Synthetic review"}
ROUTES = [("POST", ACT, PAYLOAD), ("GET", ACT, None), ("GET", ATT, None),
          ("GET", ATT + "/review-content", None), ("POST", ATT + "/review", REVIEW)]


@pytest.mark.parametrize("method,path,payload", ROUTES)
def test_attempt_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["author", "instructor", "integration"])
def test_attempt_learner_role(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in ROUTES[:3]:
        assert client.request(method, path, json=payload, headers=role_headers[role]).status_code == 403


@pytest.mark.parametrize("role", ["author", "learner", "integration"])
def test_attempt_review_role_and_spoofing(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in ROUTES[3:]:
        assert client.request(method, path, json=payload, headers={**role_headers[role], "X-Role": "instructor"}).status_code == 403


@pytest.mark.parametrize("changes", [{"score": 1}, {"points": 1}, {"learner_id": str(uuid4())},
    {"scorer_version": "trusted"}, {"evidence": []}, {"reviewed_by": "instructor"},
    {"idempotency_key": "invalid"}, {"response": {"activity_type": "selected_response", "choice_id": "a", "score": 1}},
    {"response": {"activity_type": "constructed_response", "text": " "}},
    {"response": {"activity_type": "constructed_response", "text": "x" * 10001}},
    {"response": {"activity_type": "worked_example"}}, {"response": {"activity_type": "selected_response", "choice_id": 1}}])
def test_attempt_forbids_authoritative_fields_and_invalid_answers(client, role_headers, changes):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ACT, headers=role_headers["learner"], json={**PAYLOAD, **changes}).status_code == 422


@pytest.mark.parametrize("changes", [{"score": 2}, {"scorer_version": "override"}, {"note": " "},
    {"criteria": []}, {"criteria": [{"code": "FOCUS", "points": True}]},
    {"criteria": [{"code": "FOCUS", "points": 0.5}]}, {"criteria": [{"code": "FOCUS", "points": "1"}]},
    {"criteria": [{"code": "FOCUS", "points": -1}]}])
def test_instructor_review_schema_is_strict(client, role_headers, changes):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ATT + "/review", headers=role_headers["instructor"], json={**REVIEW, **changes}).status_code == 422


@pytest.mark.parametrize("table", ["attempts", "attempt_scores", "evidence"])
def test_readiness_requires_attempt_migration(client, table):
    class Missing:
        def execute(self, query):
            if "FROM " + table + " " in str(query):
                raise OperationalError("private SQL", {}, Exception("private"))
    app.dependency_overrides[get_session] = lambda: Missing()
    assert client.get("/health/ready").json() == {"detail": "Database operation unavailable"}


def test_attempt_openapi_security_and_immutable_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path, methods in {
        "/api/v1/activities/{activity_id}/attempts": {"get", "post"},
        "/api/v1/attempts/{attempt_id}": {"get"},
        "/api/v1/attempts/{attempt_id}/review-content": {"get"},
        "/api/v1/attempts/{attempt_id}/review": {"post"},
    }.items():
        assert set(paths[path]) == methods
        for method in methods:
            assert paths[path][method]["security"] == [{"APIKeyHeader": []}]
