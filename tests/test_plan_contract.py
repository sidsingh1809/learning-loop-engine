from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

LP = "/api/v1/learners/" + str(uuid4()) + "/loop-plans"
PP = "/api/v1/loop-plans/" + str(uuid4())
PAYLOAD = {name: str(uuid4()) for name in ["enrollment_id", "target_skill_id", "learning_science_policy_id", "safety_policy_id"]}
PAYLOAD["time_budget_minutes"] = 25


@pytest.mark.parametrize("method,path,payload", [("POST", LP, PAYLOAD), ("GET", PP, None)])
def test_plans_require_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["author", "instructor", "integration"])
def test_plans_require_learner_role(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    spoof = {**role_headers[role], "X-Role": "learner"}
    assert client.post(LP, headers=spoof, json=PAYLOAD).status_code == 403
    assert client.get(PP, headers=spoof).status_code == 403


@pytest.mark.parametrize("changes", [{"time_budget_minutes": x} for x in [0, 181, True, "25", None]] + [
    {"band": "secure"}, {"states": []}, {"support_level": "minimal"}, {"rationale": "Override"},
    {"created_by": "other"}, {"target_skill_id": "bad"}, {"learning_science_policy_id": "bad"}])
def test_planning_input_cannot_override_state_or_decision(client, role_headers, changes):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(LP, headers=role_headers["learner"], json={**PAYLOAD, **changes}).status_code == 422


@pytest.mark.parametrize("table", ["loop_plans", "loop_steps"])
def test_readiness_requires_planner_migration(client, table):
    class Missing:
        def execute(self, query):
            if "FROM " + table + " " in str(query):
                raise OperationalError("private SQL", {}, Exception("private data"))
    app.dependency_overrides[get_session] = lambda: Missing()
    assert client.get("/health/ready").status_code == 503


def test_plan_openapi_is_authenticated_and_immutable(client):
    paths = client.get("/openapi.json").json()["paths"]
    create = paths["/api/v1/learners/{learner_id}/loop-plans"]
    read = paths["/api/v1/loop-plans/{plan_id}"]
    assert set(create) == {"post"} and set(read) == {"get"}
    for op in [create["post"], read["get"]]:
        assert op["security"] == [{"APIKeyHeader": []}]
    assert {"200", "201", "409"} <= set(create["post"]["responses"])
