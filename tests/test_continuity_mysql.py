from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import OperationalError

from app.models import (ActivityCompletion, ActivityGeneration, AttemptScore, Evidence, ReviewSchedule, StateApplication)
from tests.test_attempts_mysql import answer, beginner_generation, ready, review_payload
from tests.test_catalog_mysql import policies
from tests.test_domains_mysql import create
from tests.test_generation_mysql import generated
from tests.test_plans_mysql import planning

pytestmark = pytest.mark.mysql


def test_resume_retains_exact_sequence_and_attempts(mysql_client, mysql_engine, role_headers, ready):
    ap, generation, gp, plan, _, ep = ready
    key = role_headers["learner"]
    before = mysql_client.get(ep + "/state", headers=key).json()
    initial = mysql_client.get(gp + "/progress", headers=key).json()
    support = "/api/v1/activities/" + generation["activities"][0]["id"]
    assert initial["next_activity_id"] == generation["activities"][0]["id"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(support + "/completion", headers=key, json={}), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 200, 201]
    assert all(r.json() == replies[0].json() for r in replies)
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    resumed = mysql_client.get(gp + "/progress", headers=key).json()
    assert resumed["next_activity_id"] == generation["activities"][-1]["id"]
    assert resumed["steps"][0]["status"] == "completed"
    attempt, path = create(mysql_client, key, ap + "/attempts", answer())
    waiting = mysql_client.get(gp + "/progress", headers=key).json()
    assert waiting["status"] == "pending_review"
    assert waiting["steps"][-1]["attempt_ids"] == [attempt["id"]]
    assert mysql_client.get(gp + "/progress", headers=key).json() == waiting
    assert mysql_client.post(ap + "/completion", headers=key, json={}).status_code == 409
    review = review_payload(mysql_client, path, role_headers["instructor"])
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).status_code == 200
    complete = mysql_client.get(gp + "/progress", headers=key).json()
    assert complete["status"] == "completed" and complete["next_activity_id"] is None
    history = mysql_client.get(ep + "/loop-plans", headers=key).json()
    assert history["items"] == [plan]
    assert mysql_client.get(ep + "/loop-plans?limit=1&offset=1", headers=key).json()["items"] == []
    assert mysql_client.get("/api/v1/loop-plans/" + plan["id"], headers=key).json() == plan
    assert mysql_client.post(support + "/completion", headers=key, json={}).json() == replies[0].json()
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityCompletion)) == 1


def test_context_history_isolated_reviewed_and_idempotent(mysql_client, role_headers, planning):
    key, instructor = role_headers["learner"], role_headers["instructor"]
    original, gp, plan, _, ep = generated(mysql_client, key, planning)
    route = "/api/v1/loop-plans/" + plan["id"] + "/generations"
    payload = {"context_variant": "positive-donations-v1"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(route, headers=key, json=payload), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 200, 201]
    alternate = replies[0].json()
    assert alternate["id"] != original["id"] and alternate["content_hash"] != original["content_hash"]
    assert all(r.json() == alternate for r in replies)
    assert {g["id"] for g in mysql_client.get(route, headers=key).json()["items"]} == {original["id"], alternate["id"]}
    assert len(mysql_client.get(route + "?limit=1&offset=1", headers=key).json()["items"]) == 1
    agp = "/api/v1/activity-generations/" + alternate["id"]
    assert mysql_client.get(agp + "/progress", headers=key).json()["status"] == "awaiting_approval"
    assert mysql_client.get(agp + "/progress", headers=key).json()["next_activity_id"] is None
    ap = "/api/v1/activities/" + alternate["activities"][0]["id"]
    assert mysql_client.post(ap + "/completion", headers=key, json={}).status_code == 404
    assert mysql_client.get(ap, headers=key).status_code == 404
    assert mysql_client.post(agp + "/review", headers=instructor, json={"decision": "approved", "note": "Inspect alternate."}).status_code == 200
    delivered = mysql_client.get(ap, headers=key)
    assert delivered.status_code == 200 and "donations" in delivered.text
    assert mysql_client.get(gp, headers=key).json() == original
    # Each principal must own the complete path, even when IDs are known.
    for path in [route, agp + "/progress", ep + "/loop-plans", ep + "/reviews"]:
        assert mysql_client.get(path, headers=role_headers["learner2"]).status_code == 404
    assert mysql_client.post(ap + "/completion", headers=role_headers["learner2"], json={}).status_code == 404
    assert mysql_client.post(gp + "/review", headers=instructor, json={"decision": "rejected", "note": "Synthetic rejection"}).status_code == 200
    assert mysql_client.get(gp + "/progress", headers=key).json()["status"] == "rejected"


def test_review_becomes_due_without_mastery_reset_and_retry_postponement(mysql_client, mysql_engine, role_headers, ready, monkeypatch):
    import app.continuity as api
    ap, _, _, _, _, ep = ready
    learner, instructor = role_headers["learner"], role_headers["instructor"]
    assert mysql_client.get(ep + "/reviews?due_only=false", headers=learner).json()["items"] == []
    last_payload = last_review = last_path = None
    for _ in range(2):
        last_payload = answer()
        _, last_path = create(mysql_client, learner, ap + "/attempts", last_payload)
        assert mysql_client.get(ep + "/reviews?due_only=false", headers=learner).json()["items"] == ([] if last_review is None else upcoming["items"])
        last_review = review_payload(mysql_client, last_path, instructor)
        assert mysql_client.post(last_path + "/review", headers=instructor, json=last_review).status_code == 200
        upcoming = mysql_client.get(ep + "/reviews?due_only=false", headers=learner).json()
    state = mysql_client.get(ep + "/state", headers=learner).json()
    assert all(s["band"] == "secure" for s in state["items"])
    assert len(upcoming["items"]) == 2
    assert all(r["band"] == "secure" and not r["due"] for r in upcoming["items"])
    due = max(datetime.fromisoformat(r["due_at"].replace("Z", "+00:00")).replace(tzinfo=None) for r in upcoming["items"])
    for row in upcoming["items"]:
        assert datetime.fromisoformat(row["due_at"].replace("Z", "+00:00")) - datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00")) == timedelta(days=7)
    monkeypatch.setattr(api, "utc_now", lambda: due - timedelta(seconds=1))
    assert mysql_client.get(ep + "/reviews", headers=learner).json()["items"] == []
    monkeypatch.setattr(api, "utc_now", lambda: due)
    due_reviews = mysql_client.get(ep + "/reviews", headers=learner).json()["items"]
    assert all(r["due"] and r["band"] == "secure" for r in due_reviews)
    assert len(due_reviews) == 2
    assert mysql_client.get(ep + "/state", headers=learner).json() == state
    assert mysql_client.post(last_path + "/review", headers=instructor, json=last_review).status_code == 200
    assert mysql_client.post(ap + "/attempts", headers=learner, json=last_payload).status_code == 200
    assert mysql_client.post(ep + "/state/applications", headers=learner, json={}).json()["applied_count"] == 0
    assert mysql_client.get(ep + "/reviews", headers=learner).json()["items"] == due_reviews
    assert mysql_client.get(ep + "/state", headers=learner).json() == state
    # Explicit write synchronization backfills reminders from historical applied scores.
    with mysql_engine.begin() as conn:
        conn.execute(ReviewSchedule.__table__.delete())
    assert mysql_client.get(ep + "/reviews", headers=learner).json()["items"] == []
    assert mysql_client.post(ep + "/state/applications", headers=learner, json={}).json()["applied_count"] == 0
    assert mysql_client.get(ep + "/reviews", headers=learner).json()["items"] == due_reviews
    assert mysql_client.get(ep + "/state", headers=learner).json() == state


def test_part_task_does_not_schedule_or_dismiss_review(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    key, instructor = role_headers["learner"], role_headers["instructor"]
    generation, gp = beginner_generation(mysql_client, mysql_engine, key, planning)
    assert mysql_client.post(gp + "/review", headers=instructor, json={"decision": "approved", "note": "Synthetic"}).status_code == 200
    selected = next(a for a in generation["activities"] if a["activity_type"] == "selected_response")
    path = "/api/v1/activities/" + selected["id"] + "/attempts"
    create(mysql_client, key, path, {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "a"}})
    ep = planning[3]
    assert mysql_client.get(ep + "/reviews?due_only=false", headers=key).json()["items"] == []
    whole = "/api/v1/activities/" + generation["activities"][-1]["id"]
    _, attempt_path = create(mysql_client, key, whole + "/attempts", answer())
    scoring = review_payload(mysql_client, attempt_path, instructor)
    assert mysql_client.post(attempt_path + "/review", headers=instructor, json=scoring).status_code == 200
    before = mysql_client.get(ep + "/reviews?due_only=false", headers=key).json()["items"]
    create(mysql_client, key, path, {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "a"}})
    assert mysql_client.get(ep + "/reviews?due_only=false", headers=key).json()["items"] == before
    progress = mysql_client.get(gp + "/progress", headers=key).json()
    assert progress["steps"][1]["status"] == "completed"


def test_schedule_failure_rolls_back_score_state_and_evidence(mysql_client, mysql_engine, role_headers, ready):
    ap, _, _, _, _, ep = ready
    key, instructor = role_headers["learner"], role_headers["instructor"]
    _, path = create(mysql_client, key, ap + "/attempts", answer())
    review = review_payload(mysql_client, path, instructor)
    before = mysql_client.get(ep + "/state", headers=key).json()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO review_schedules"):
            raise OperationalError("private SQL", {}, Exception("private"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        result = mysql_client.post(path + "/review", headers=instructor, json=review)
        assert result.status_code == 503 and result.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(path, headers=key).json()["status"] == "pending_review"
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        for model in [ReviewSchedule, StateApplication, Evidence, AttemptScore]:
            assert conn.scalar(select(func.count()).select_from(model)) == 0
    assert mysql_client.post(path + "/review", headers=instructor, json=review).status_code == 200


def test_support_failure_and_archived_retention(mysql_client, mysql_engine, headers, role_headers, ready):
    _, generation, gp, _, pilot, _ = ready
    key = role_headers["learner"]
    path = "/api/v1/activities/" + generation["activities"][0]["id"] + "/completion"
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO activity_completions"):
            raise OperationalError("private SQL", {}, Exception("private"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        assert mysql_client.post(path, headers=key, json={}).status_code == 503
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(gp + "/progress", headers=key).json()["steps"][0]["status"] == "not_started"
    response = mysql_client.post(path, headers=key, json={})
    assert response.status_code == 201
    completion = response.json()
    assert mysql_client.post(pilot[1] + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(path, headers=key, json={}).json() == completion
    assert mysql_client.get(gp + "/progress", headers=key).status_code == 200


def test_missing_progress_and_invalid_history_pagination(mysql_client, role_headers, ready):
    key = role_headers["learner"]
    assert mysql_client.get("/api/v1/activity-generations/" + str(uuid4()) + "/progress", headers=key).status_code == 404
    assert mysql_client.post("/api/v1/activities/" + str(uuid4()) + "/completion", headers=key, json={}).status_code == 404
    for path in [ready[5] + "/loop-plans", ready[5] + "/reviews", "/api/v1/loop-plans/" + ready[3]["id"] + "/generations"]:
        for query in ["?limit=0", "?limit=101", "?offset=-1"]:
            assert mysql_client.get(path + query, headers=key).status_code == 422
