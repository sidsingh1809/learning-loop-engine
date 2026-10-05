from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.database import get_session
from app.domain_graph import topological_order
from app.main import app

PATH = "/api/v1/courses/{}/domain-versions/{}".format(uuid4(), uuid4())
EDGE = {"skill_id": str(uuid4()), "prerequisite_skill_id": str(uuid4())}


@pytest.mark.parametrize("payload", [
    {}, {"skill_id": EDGE["skill_id"]}, {**EDGE, "skill_id": "invalid"},
    {**EDGE, "prerequisite_skill_id": None}, {**EDGE, "id": str(uuid4())},
    {**EDGE, "prerequisite_skill_id": EDGE["skill_id"]},
])
def test_invalid_prerequisite_input(client, headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(PATH + "/prerequisites", headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("action", ["publish", "validate"])
@pytest.mark.parametrize("payload", [{"status": "published"}, {"published_at": "2026-10-03T00:00:00Z"}])
def test_actions_reject_client_lifecycle_fields(client, headers, action, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(PATH + "/" + action, headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("role", ["learner", "instructor", "integration"])
@pytest.mark.parametrize("method,suffix,payload", [
    ("POST", "/prerequisites", EDGE),
    ("DELETE", "/prerequisites/" + str(uuid4()), None),
    ("POST", "/publish", {}),
])
def test_graph_writes_require_author(client, role_headers, role, method, suffix, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.request(method, PATH + suffix, headers=role_headers[role], json=payload).status_code == 403


@pytest.mark.parametrize("method,suffix", [
    ("GET", "/prerequisites"), ("GET", "/prerequisites/" + str(uuid4())),
    ("POST", "/prerequisites"), ("DELETE", "/prerequisites/" + str(uuid4())),
    ("POST", "/validate"), ("POST", "/publish"),
])
def test_graph_endpoints_require_credentials(client, method, suffix):
    assert client.request(method, PATH + suffix, json=EDGE if suffix == "/prerequisites" else {}).status_code == 401


@pytest.mark.parametrize("missing", ["published_at", "skill_prerequisites"])
def test_readiness_requires_day4_migration(client, missing):
    from sqlalchemy.exc import OperationalError

    class MissingGraph:
        def execute(self, statement):
            if missing in str(statement):
                raise OperationalError("private SQL", {}, Exception("private credentials"))

    app.dependency_overrides[get_session] = lambda: MissingGraph()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}


def test_prerequisite_order_handles_long_graph_and_multiple_roots():
    # A chain beyond Python's recursion limit must still validate.
    skills = [SimpleNamespace(id=str(i), code="S{:04}".format(i)) for i in range(1500)]
    edges = [(str(i), str(i - 1)) for i in range(1, 1500)]
    assert topological_order(skills[::-1], edges[::-1]) == [str(i) for i in range(1500)]
    assert topological_order(skills, [*edges, ("0", "1499")]) is None
    roots = [SimpleNamespace(id=code, code=code) for code in ["Z", "A", "B"]]
    assert topological_order(roots, [("B", "A")]) == ["A", "B", "Z"]
    assert topological_order(roots, [("B", "FOREIGN")]) is None
