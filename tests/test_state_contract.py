from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_session
from app.main import app

PATH = "/api/v1/learners/{}/enrollments/{}/state/applications".format(uuid4(), uuid4())


def test_state_sync_security_and_body_contract(client, role_headers):
    app.dependency_overrides[get_session] = lambda: None
    assert client.post(PATH, json={}).status_code == 401
    for role in ["author", "instructor", "integration"]:
        assert client.post(PATH, headers=role_headers[role], json={}).status_code == 403
    for payload in [{"band": "secure"}, {"evidence": []}, {"policy_version": "override"}]:
        assert client.post(PATH, headers=role_headers["learner"], json=payload).status_code == 422


@pytest.mark.parametrize("missing", ["state_applications", "whole_task_attempt_count"])
def test_readiness_checks_application_migration(client, missing):
    class Unmigrated:
        def execute(self, query):
            if missing in str(query):
                raise OperationalError("private SQL", {}, Exception("private detail"))
    app.dependency_overrides[get_session] = lambda: Unmigrated()
    result = client.get("/health/ready")
    assert result.status_code == 503 and result.json() == {"detail": "Database operation unavailable"}
