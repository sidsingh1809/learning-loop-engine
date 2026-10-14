from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

ID = str(uuid4())
ROUTES = [("GET", f"/api/v1/learners/{ID}/enrollments/{ID}/loop-plans", None),
          ("GET", f"/api/v1/loop-plans/{ID}/generations", None),
          ("GET", f"/api/v1/activity-generations/{ID}/progress", None),
          ("POST", f"/api/v1/activities/{ID}/completion", {}),
          ("GET", f"/api/v1/learners/{ID}/enrollments/{ID}/reviews", None)]


@pytest.mark.parametrize("method,path,payload", ROUTES)
def test_continuity_requires_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("role", ["author", "integration", "instructor"])
def test_continuity_requires_learner(client, role_headers, role):
    app.dependency_overrides[get_session] = lambda: None
    for method, path, payload in ROUTES:
        assert client.request(method, path, json=payload, headers=role_headers[role]).status_code == 403


@pytest.mark.parametrize("payload", [{"score": 1}, {"band": "secure"}, {"completed": True}])
def test_completion_cannot_supply_state(client, role_headers, payload):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(ROUTES[3][1], headers=role_headers["learner"], json=payload).status_code == 422


@pytest.mark.parametrize("table", ["review_schedules", "activity_completions"])
def test_readiness_requires_continuity_migration(client, table):
    class Missing:
        def execute(self, query):
            if "FROM " + table + " " in str(query):
                raise OperationalError("private SQL", {}, Exception("private"))
    app.dependency_overrides[get_session] = lambda: Missing()
    assert client.get("/health/ready").status_code == 503
