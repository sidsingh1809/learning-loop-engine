from uuid import uuid4

import pytest

from app.database import get_session
from app.main import app

BASE = "/api/v1/courses/{}/domain-versions".format(uuid4())
VERSION = BASE + "/" + str(uuid4())
COMPETENCY = {"code": "DEBUG", "statement": "Diagnose a small program"}
SKILL = {"code": "VARIABLES", "title": "Trace variables", "skill_kind": "routine", "competency_id": str(uuid4())}


@pytest.mark.parametrize("route,payload", [
    (BASE, {"version": 10}), (BASE, {"status": "published"}),
    (VERSION + "/competencies", {**COMPETENCY, "code": "bad code"}),
    (VERSION + "/competencies", {**COMPETENCY, "statement": " "}),
    (VERSION + "/competencies", {**COMPETENCY, "statement": "x" * 10001}),
    (VERSION + "/skills", {**SKILL, "skill_kind": "unknown"}),
    (VERSION + "/skills", {**SKILL, "title": " "}),
    (VERSION + "/skills", {**SKILL, "requires_automaticity": "false"}),
    (VERSION + "/skills", {**SKILL, "requires_automaticity": True, "skill_kind": "non_routine"}),
    (VERSION + "/skills", {**SKILL, "domain_version_id": str(uuid4())}),
    (VERSION + "/skills", {**SKILL, "competency_id": "invalid"}),
])
def test_invalid_domain_creation(client, headers, route, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(route, headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("resource,payload", [
    ("competencies", {}), ("competencies", {"statement": None}),
    ("competencies", {"code": None}), ("competencies", {"domain_version_id": str(uuid4())}),
    ("skills", {}), ("skills", {"title": None}), ("skills", {"description": None}),
    ("skills", {"requires_automaticity": None}), ("skills", {"skill_kind": None}),
    ("skills", {"competency_id": str(uuid4())}), ("skills", {"requires_automaticity": 1}),
])
def test_invalid_domain_patch(client, headers, resource, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.patch(VERSION + "/" + resource + "/" + str(uuid4()), headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("role", ["learner", "instructor", "integration"])
@pytest.mark.parametrize("method,route,payload", [
    ("POST", BASE, {}), ("POST", VERSION + "/competencies", COMPETENCY),
    ("POST", VERSION + "/skills", SKILL),
    ("PATCH", VERSION + "/competencies/" + str(uuid4()), {"statement": "Changed"}),
    ("PATCH", VERSION + "/skills/" + str(uuid4()), {"title": "Changed"}),
])
def test_domain_writes_require_author(client, role_headers, role, method, route, payload):
    app.dependency_overrides[get_session] = lambda: None
    spoofed = {**role_headers[role], "X-Subject": "dev-author", "X-Role": "author"}
    assert client.request(method, route, headers=spoofed, json=payload).status_code == 403


def test_domain_auth_and_openapi(client):
    for route in [BASE, VERSION, VERSION + "/competencies", VERSION + "/skills"]:
        assert client.get(route).status_code == 401
    schema = client.get("/openapi.json").json()
    routes = {path: methods for path, methods in schema["paths"].items() if "domain-versions" in path}
    assert len(routes) == 6
    for methods in routes.values():
        assert "delete" not in methods
        for operation in methods.values():
            assert operation["security"] == [{"APIKeyHeader": []}]


def test_readiness_requires_domain_migration(client):
    from sqlalchemy.exc import OperationalError

    class MissingDomain:
        def execute(self, statement):
            if "domain_versions" in str(statement):
                raise OperationalError("SELECT private data", {}, Exception("missing table"))

    app.dependency_overrides[get_session] = lambda: MissingDomain()
    assert client.get("/health/ready").json() == {"detail": "Database operation unavailable"}
    assert client.get("/health/ready").status_code == 503
