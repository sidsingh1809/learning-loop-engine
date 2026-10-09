from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

CREATE = "/api/v1/loop-plans/" + str(uuid4()) + "/generations"
GEN = "/api/v1/activity-generations/" + str(uuid4())
ACT = "/api/v1/activities/" + str(uuid4())
ROUTES = [("POST", CREATE, {}), ("GET", GEN, None), ("GET", ACT, None),
          ("GET", GEN + "/review-content", None), ("POST", GEN + "/review", {"decision": "approved", "note": "Synthetic"})]


@pytest.mark.parametrize("method,path,payload", ROUTES)
def test_generation_requires_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["author", "integration", "instructor"])
def test_generation_and_delivery_require_learner(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in ROUTES[:3]:
        assert client.request(method, path, json=payload, headers=role_headers[role]).status_code == 403


@pytest.mark.parametrize("role", ["author", "integration", "learner"])
def test_review_requires_instructor(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in ROUTES[3:]:
        assert client.request(method, path, json=payload, headers={**role_headers[role], "X-Role": "instructor"}).status_code == 403


@pytest.mark.parametrize("payload", [{"steps": []}, {"provider": "AI"}, {"content": "override"},
                                      {"review_status": "approved"}, {"score": 1}, {"template_version": "other"}])
def test_clients_cannot_override_generation(client, role_headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(CREATE, headers=role_headers["learner"], json=payload).status_code == 422


@pytest.mark.parametrize("table", ["activity_generations", "activities"])
def test_readiness_requires_generation_migration(client, table):
    class Missing:
        def execute(self, query):
            if "FROM " + table + " " in str(query):
                raise OperationalError("secret SQL", {}, Exception("secret"))
    app.dependency_overrides[get_session] = lambda: Missing()
    assert client.get("/health/ready").status_code == 503


def test_generation_openapi_documents_security_and_immutable_reads(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {"/api/v1/loop-plans/{plan_id}/generations": {"post"},
                "/api/v1/activity-generations/{generation_id}": {"get"},
                "/api/v1/activity-generations/{generation_id}/review-content": {"get"},
                "/api/v1/activity-generations/{generation_id}/review": {"post"},
                "/api/v1/activities/{activity_id}": {"get"}}
    for path, methods in expected.items():
        assert set(paths[path]) == methods
        for method in methods: assert paths[path][method]["security"] == [{"APIKeyHeader": []}]
