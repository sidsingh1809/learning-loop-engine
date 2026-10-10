from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Attempt, AttemptScore, Evidence, LearnerSkillState, StateApplication
from tests.test_attempts_mysql import answer, beginner_generation, ready, review_payload
from tests.test_catalog_mysql import policies
from tests.test_domains_mysql import create
from tests.test_plans_mysql import planning

pytestmark = pytest.mark.mysql


def scored(client, roles, activity, points=None):
    payload = answer()
    attempt, path = create(client, roles["learner"], activity + "/attempts", payload)
    assert attempt["state_application"] is None
    review = review_payload(client, path, roles["instructor"])
    if points is not None:
        review["criteria"] = [{**c, "points": points} for c in review["criteria"]]
    result = client.post(path + "/review", headers=roles["instructor"], json=review)
    assert result.status_code == 200, result.text
    return result.json(), path, payload, review


def test_full_loop_unknown_developing_secure_and_faded_next_plan(mysql_client, mysql_engine, role_headers, ready, planning):
    ap, _, _, original, _, ep = ready
    key = role_headers["learner"]
    state = lambda: mysql_client.get(ep + "/state", headers=key).json()
    assert all(s["band"] == "unknown" for s in state()["items"])
    first, path, payload, review = scored(mysql_client, role_headers, ap)
    after = state()
    assert all(s["band"] == "developing" and s["whole_task_attempt_count"] == 1 for s in after["items"])
    assert all(c["before"]["band"] == "unknown" and c["after"]["band"] == "developing"
               for c in first["state_application"]["changes"])
    next_plan, pp = create(mysql_client, key, planning[0], planning[1])
    assert next_plan["id"] != original["id"] and next_plan["decision"]["action"] == "guided_practice"
    assert any(s["role"] == "focus_practice" for s in next_plan["decision"]["steps"])
    assert all(s["policy_version"] == "provisional-mastery-v1" for s in next_plan["input_snapshot"]["states"])
    # Generate and deliver the new plan, then use live evidence for part-task scoring.
    generation, gp = create(mysql_client, key, pp + "/generations", {})
    candidate = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).json()["candidate"]
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"],
        json={"decision": "approved", "note": "Synthetic loop acceptance"}).status_code == 200
    practice = next(a for a in generation["activities"] if a["activity_type"] == "selected_response")
    step = next(s for s in candidate["steps"] if s["position"] == practice["position"])
    practice_path = "/api/v1/activities/" + practice["id"] + "/attempts"
    from uuid import uuid4
    selected = {"idempotency_key": str(uuid4()), "response": {
        "activity_type": "selected_response", "choice_id": step["content"]["correct_choice_id"]}}
    response, _ = create(mysql_client, key, practice_path, selected)
    after_practice = state()
    assert all(s["band"] == "developing" and s["whole_task_attempt_count"] == 1 for s in after_practice["items"])
    assert sum(s["part_task_evidence_count"] for s in after_practice["items"]) == 1
    assert mysql_client.post(practice_path, headers=key, json=selected).json() == response
    whole = next(a for a in generation["activities"] if a["activity_type"] == "constructed_response")
    second, _, _, _ = scored(mysql_client, role_headers, "/api/v1/activities/" + whole["id"])
    assert all(s["band"] == "secure" and s["whole_task_attempt_count"] == 2 for s in state()["items"])
    independent, _ = create(mysql_client, key, planning[0], planning[1])
    assert independent["decision"]["action"] == "independent_task"
    assert independent["decision"]["support_level"] == "minimal"
    assert [s["role"] for s in independent["decision"]["steps"]] == ["whole_task"]
    before_retry = state()
    assert mysql_client.post(ap + "/attempts", headers=key, json=payload).json() == first
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).json() == first
    assert state() == before_retry
    assert mysql_client.get("/api/v1/loop-plans/" + original["id"], headers=key).json() == original
    assert second["state_application"]["formal_certification"] is False
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(StateApplication)) == 3
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 5


@pytest.mark.parametrize("failure", ["UPDATE learner_skill_states", "INSERT INTO state_applications"])
def test_state_or_history_failure_rolls_back_new_score_and_evidence(mysql_client, mysql_engine, role_headers, ready, failure):
    ap, _, _, _, _, ep = ready
    learner = role_headers["learner"]
    before = mysql_client.get(ep + "/state", headers=learner).json()
    attempt, path = create(mysql_client, learner, ap + "/attempts", answer())
    review = review_payload(mysql_client, path, role_headers["instructor"])
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(failure):
            raise OperationalError("private SQL", {}, Exception("private response"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        result = mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review)
        assert result.status_code == 503 and result.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(path, headers=learner).json() == attempt
    assert mysql_client.get(ep + "/state", headers=learner).json() == before
    with mysql_engine.connect() as conn:
        for model in [AttemptScore, Evidence, StateApplication]:
            assert conn.scalar(select(func.count()).select_from(model)) == 0
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).status_code == 200


@pytest.mark.parametrize("trigger", ["sync", "plan", "submission_retry", "review_retry"])
def test_existing_day9_scores_apply_once_without_rewriting_evidence(mysql_client, mysql_engine, monkeypatch, role_headers, ready, planning, trigger):
    import app.attempts as routes
    with monkeypatch.context() as patch:
        patch.setattr(routes, "apply_pending_scores", lambda enrollment, session: 0)
        first, path, payload, review = scored(mysql_client, role_headers, ready[0])
    assert first["state_application"] is None
    with mysql_engine.connect() as conn:
        evidence_before = conn.execute(select(Evidence)).mappings().all()
    key = role_headers["learner"]
    sync = ready[5] + "/state/applications"
    if trigger == "sync":
        assert mysql_client.post(sync, headers=key, json={}).json()["applied_count"] == 1
    elif trigger == "plan":
        assert mysql_client.post(planning[0], headers=key, json=planning[1]).status_code == 201
    elif trigger == "submission_retry":
        assert mysql_client.post(ready[0] + "/attempts", headers=key, json=payload).status_code == 200
    else:
        assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).status_code == 200
    after = mysql_client.get(ready[5] + "/state", headers=key).json()
    assert all(s["revision"] == 1 for s in after["items"])
    assert mysql_client.get(path, headers=key).json()["state_application"] is not None
    assert mysql_client.post(sync, headers=key, json={}).json()["applied_count"] == 0
    assert mysql_client.get(ready[5] + "/state", headers=key).json() == after
    with mysql_engine.connect() as conn:
        assert conn.execute(select(Evidence)).mappings().all() == evidence_before


def test_distinct_concurrent_reviews_and_retries_never_lose_revisions(mysql_client, mysql_engine, role_headers, ready):
    key, instructor = role_headers["learner"], role_headers["instructor"]
    paths = [create(mysql_client, key, ready[0] + "/attempts", answer())[1] for _ in range(3)]
    review = review_payload(mysql_client, paths[0], instructor)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: mysql_client.post(p + "/review", headers=instructor, json=review), paths + paths))
    assert all(r.status_code == 200 for r in results)
    states = mysql_client.get(ready[5] + "/state", headers=key).json()["items"]
    assert all(s["revision"] == s["whole_task_attempt_count"] == 3 and s["band"] == "secure" for s in states)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(StateApplication)) == 3
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 6


def test_sync_isolation_strict_body_and_archived_pending_scores(mysql_client, headers, role_headers, ready, monkeypatch):
    import app.attempts as routes
    with monkeypatch.context() as patch:
        patch.setattr(routes, "apply_pending_scores", lambda enrollment, session: 0)
        scored(mysql_client, role_headers, ready[0])
    route = ready[5] + "/state/applications"
    assert mysql_client.post(route, json={}).status_code == 401
    for role in ["author", "instructor", "integration"]:
        assert mysql_client.post(route, headers=role_headers[role], json={}).status_code == 403
    assert mysql_client.post(route, headers=role_headers["learner2"], json={}).status_code == 404
    assert mysql_client.post(route, headers=role_headers["learner"], json={"band": "secure"}).status_code == 422
    assert mysql_client.post(ready[4][1] + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(route, headers=role_headers["learner"], json={}).json()["applied_count"] == 1


def test_database_enforces_observation_and_whole_task_boundaries(mysql_client, mysql_engine, role_headers, ready):
    scored(mysql_client, role_headers, ready[0])
    for statement, error in [
        (update(LearnerSkillState).values(band="unknown"), OperationalError),
        (update(LearnerSkillState).values(band="secure"), OperationalError),
        (update(LearnerSkillState).values(evidence_count=0), OperationalError),
        (update(LearnerSkillState).values(policy_version=None), OperationalError),
        (update(StateApplication).values(formal_certification=True), OperationalError),
        (update(StateApplication).values(enrollment_id="missing"), IntegrityError),
    ]:
        with mysql_engine.connect() as conn:
            with pytest.raises(error):
                conn.execute(statement)
            conn.rollback()


@pytest.mark.parametrize("failure", ["UPDATE learner_skill_states", "INSERT INTO state_applications"])
def test_selected_state_failure_rolls_back_entire_submission(mysql_client, mysql_engine, role_headers, planning, failure):
    from uuid import uuid4
    key = role_headers["learner"]
    generation, gp = beginner_generation(mysql_client, mysql_engine, key, planning)
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"],
        json={"decision": "approved", "note": "Synthetic selected rollback check"}).status_code == 200
    activity = next(a for a in generation["activities"] if a["activity_type"] == "selected_response")
    path = "/api/v1/activities/" + activity["id"] + "/attempts"
    payload = {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "a"}}
    before = mysql_client.get(planning[3] + "/state", headers=key).json()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(failure):
            raise OperationalError("private SQL", {}, Exception("private response"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        result = mysql_client.post(path, headers=key, json=payload)
        assert result.status_code == 503
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(planning[3] + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        for model in [Attempt, AttemptScore, Evidence, StateApplication]:
            assert conn.scalar(select(func.count()).select_from(model)) == 0
    assert mysql_client.post(path, headers=key, json=payload).status_code == 201


def test_historical_batch_failure_and_concurrent_sync_are_atomic(mysql_client, mysql_engine, role_headers, ready, monkeypatch):
    import app.attempts as routes
    with monkeypatch.context() as patch:
        patch.setattr(routes, "apply_pending_scores", lambda enrollment, session: 0)
        for _ in range(2):
            scored(mysql_client, role_headers, ready[0])
    key = role_headers["learner"]
    before = mysql_client.get(ready[5] + "/state", headers=key).json()
    inserts = []
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO state_applications"):
            inserts.append(statement)
            if len(inserts) == 2:
                raise OperationalError("private SQL", {}, Exception("private response"))
    route = ready[5] + "/state/applications"
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        assert mysql_client.post(route, headers=key, json={}).status_code == 503
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(ready[5] + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(StateApplication)) == 0
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 4
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: mysql_client.post(route, headers=key, json={}), range(3)))
    assert all(r.status_code == 200 for r in results)
    assert sorted(r.json()["applied_count"] for r in results) == [0, 0, 2]
    assert all(s["revision"] == 2 for s in mysql_client.get(ready[5] + "/state", headers=key).json()["items"])


def test_downgrade_refuses_observed_state_before_ddl(mysql_client, mysql_engine, role_headers, ready, monkeypatch):
    import os
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text
    from app.config import get_settings
    from app.database import get_engine
    scored(mysql_client, role_headers, ready[0])
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Cannot downgrade observed learner state"):
            command.downgrade(Config("alembic.ini"), "0009_attempts")
        assert "state_applications" in inspect(mysql_engine).get_table_names()
        with mysql_engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0010_state_application"
            assert conn.scalar(select(func.count()).select_from(StateApplication)) == 1
    finally:
        get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
