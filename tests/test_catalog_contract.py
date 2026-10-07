import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

EXAMPLES = json.loads((Path(__file__).resolve().parents[1] / "app/synthetic_catalog.json").read_text())
ROOT = "/api/v1/catalog"
VERSION_ID = str(uuid4())
POLICY = EXAMPLES["policies"][0]
ACTIVITY = {**EXAMPLES["activities"][0], "learning_science_policy_id": str(uuid4()), "safety_policy_id": str(uuid4())}
OPERATIONS = [("GET", ROOT + "/" + kind + suffix, None)
              for kind in ["policies", "activities", "policy-versions", "activity-versions"]
              for suffix in ["", "/" + VERSION_ID]] + [
    ("POST", ROOT + "/policy-versions", POLICY),
    ("POST", ROOT + "/activity-versions", ACTIVITY),
    ("POST", ROOT + "/policy-versions/" + VERSION_ID + "/review", {"decision": "approved", "note": "Synthetic review"}),
    ("POST", ROOT + "/activity-versions/" + VERSION_ID + "/review", {"decision": "approved", "note": "Synthetic review"}),
]


@pytest.mark.parametrize("method,path,payload", OPERATIONS)
def test_catalog_requires_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["learner", "integration", "instructor"])
def test_catalog_creation_requires_author(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for kind, payload in [("policy", POLICY), ("activity", ACTIVITY)]:
        assert client.post(ROOT + "/" + kind + "-versions", headers=role_headers[role], json=payload).status_code == 403


@pytest.mark.parametrize("role", ["author", "learner", "integration"])
def test_catalog_review_requires_instructor(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for kind in ["policy", "activity"]:
        response = client.post(ROOT + "/" + kind + "-versions/" + VERSION_ID + "/review",
                               headers={**role_headers[role], "X-Role": "instructor"},
                               json={"decision": "approved", "note": "Synthetic review"})
        assert response.status_code == 403


@pytest.mark.parametrize("role", ["learner", "integration"])
def test_consumers_cannot_read_authoring_versions(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for kind in ["policy", "activity"]:
        for suffix in ["", "/" + VERSION_ID]:
            assert client.get(ROOT + "/" + kind + "-versions" + suffix, headers=role_headers[role]).status_code == 403


@pytest.mark.parametrize("changes", [
    {"version": 0}, {"version": True}, {"version": "1"}, {"version": 2147483648}, {"title": "  "},
    {"references": []}, {"references": [" "]}, {"category": "mastery"},
    {"review_status": "approved"}, {"reviewed_by": "instructor"}, {"review_scope": "university"},
    {"rules": {}}, {"rules": {**POLICY["rules"], "formal_certification": True}},
    {"rules": {**POLICY["rules"], "part_task_practice": "any_skill"}},
    {"rules": {**POLICY["rules"], "mastery_threshold": 0.8}},
    {"category": "safety"},
])
def test_policy_rejects_invalid_or_unsafe_contract(client, headers, changes):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ROOT + "/policy-versions", headers=headers, json={**POLICY, **changes}).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("data", "real_students"), ("generated_content", "automatically_approved"),
    ("learner_input", "instructions"), ("code_execution", "enabled"),
    ("client_authoritative_scores", "allowed"), ("constructed_response_scoring", "automatic"),
    ("university_review_required", False),
])
def test_safety_policy_cannot_relax_prototype_boundaries(client, headers, field, value):
    app.dependency_overrides[get_session] = lambda: None
    payload = EXAMPLES["policies"][1]
    payload = {**payload, "rules": {**payload["rules"], field: value}}
    assert client.post(ROOT + "/policy-versions", headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("changes", [
    {"mappings": []}, {"mappings": [{"component": "quiz", "rationale": "Wrong component"}]},
    {"mappings": ACTIVITY["mappings"] * 2}, {"activity_type": "code_execution"},
    {"estimated_minutes": 0}, {"estimated_minutes": 181}, {"estimated_minutes": True},
    {"safety_policy_id": "bad"}, {"review_status": "approved"}, {"evidence_tier": "established"},
    {"purpose": " "}, {"guidance": " "}, {"mappings": [{"component": "learning_tasks", "rationale": " "}]},
])
def test_activity_rejects_invalid_or_authoritative_fields(client, headers, changes):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ROOT + "/activity-versions", headers=headers, json={**ACTIVITY, **changes}).status_code == 422


@pytest.mark.parametrize("payload", [{"decision": "draft", "note": "No"}, {"decision": "approved", "note": " "},
                                      {"decision": "approved", "note": "Yes", "review_scope": "university"}])
def test_review_rejects_invalid_decisions_and_scope(client, role_headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ROOT + "/policy-versions/" + VERSION_ID + "/review", headers=role_headers["instructor"], json=payload).status_code == 422


@pytest.mark.parametrize("table", ["policy_versions", "activity_variants", "component_activity_mappings"])
def test_readiness_requires_catalog_migration(client, table):
    class MissingCatalogSession:
        def execute(self, statement):
            if "FROM " + table + " " in str(statement):
                raise OperationalError("private SQL", {}, Exception("private connection"))
    app.dependency_overrides[get_session] = lambda: MissingCatalogSession()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}


def test_openapi_catalog_security_and_immutable_surface(client):
    paths = client.get("/openapi.json").json()["paths"]
    operations = [operation for path, methods in paths.items() if path.startswith(ROOT) for operation in methods.values()]
    assert len(operations) == 12
    assert all(operation["security"] == [{"APIKeyHeader": []}] for operation in operations)
    assert all(set(methods) <= {"post", "get"} for path, methods in paths.items() if path.startswith(ROOT))
