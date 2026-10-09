from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Activity, ActivityGeneration
from app.generator import build_sequence, content_hash
from app.planner_schemas import DecisionRead, PlannerInput
from tests.test_plans_mysql import planning
from tests.test_catalog_mysql import policies
from tests.test_domains_mysql import create

pytestmark = pytest.mark.mysql


def generated(client, key, planning):
    route, payload, pilot, ep, _ = planning
    plan, pp = create(client, key, route, payload)
    generation, gp = create(client, key, pp + "/generations", {})
    return generation, gp, plan, pilot, ep


def test_generation_review_delivery_replay_and_state_unchanged(mysql_client, mysql_engine, role_headers, planning):
    key = role_headers["learner"]
    ep = planning[3]
    before = mysql_client.get(ep + "/state", headers=key).json()
    generation, gp, plan, _, _ = generated(mysql_client, key, planning)
    assert generation["review_status"] == "draft"
    assert [a["role"] for a in generation["activities"]] == ["whole_task_context", "whole_task_return"]
    assert "content" not in str(generation["activities"])
    route = "/api/v1/loop-plans/" + plan["id"] + "/generations"
    retry = mysql_client.post(route, headers=key, json={})
    assert retry.status_code == 200 and retry.json() == generation
    assert mysql_client.get(gp, headers=key).json() == generation
    ap = "/api/v1/activities/" + generation["activities"][0]["id"]
    assert mysql_client.get(ap, headers=key).status_code == 404
    review = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"])
    assert review.status_code == 200, review.text
    snapshot, decision = PlannerInput(**plan["input_snapshot"]), DecisionRead(**plan["decision"])
    expected = build_sequence(snapshot, decision)
    assert review.json()["candidate"] == expected.model_dump(mode="json")
    assert generation["content_hash"] == content_hash(expected)
    payload = {"decision": "approved", "note": "Synthetic content and rubric inspected."}
    approved = mysql_client.post(gp + "/review", headers=role_headers["instructor"], json=payload)
    assert approved.status_code == 200, approved.text
    assert approved.json()["reviewed_by"] == "other-instructor"
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json=payload).json() == approved.json()
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={**payload, "decision": "rejected"}).status_code == 409
    delivered = [mysql_client.get("/api/v1/activities/" + a["id"], headers=key) for a in generation["activities"]]
    assert all(r.status_code == 200 for r in delivered)
    assert delivered[-1].json()["step"]["rubric"]["scoring_method"] == "instructor_review"
    assert all("expected_response" not in r.text and "correct_choice_id" not in r.text for r in delivered)
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 1
        assert conn.scalar(select(func.count()).select_from(Activity)) == 2


def test_candidate_isolation_rejection_and_immutable_routes(mysql_client, headers, role_headers, planning):
    key = role_headers["learner"]
    generation, gp, plan, _, _ = generated(mysql_client, key, planning)
    route = "/api/v1/loop-plans/" + plan["id"] + "/generations"
    ap = "/api/v1/activities/" + generation["activities"][0]["id"]
    other = {**role_headers["learner2"], "X-Subject": "other-learner"}
    assert mysql_client.post(route, headers=other, json={}).status_code == 404
    assert mysql_client.get(gp, headers=other).status_code == 404
    assert mysql_client.get(ap, headers=other).status_code == 404
    assert mysql_client.get(gp + "/review-content", headers=key).status_code == 403
    assert mysql_client.post(gp + "/review", headers=key, json={"decision": "approved", "note": "self"}).status_code == 403
    rejected = mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "rejected", "note": "Revise content."})
    assert rejected.status_code == 200
    assert mysql_client.get(ap, headers=key).status_code == 404
    assert mysql_client.post(route, headers=key, json={}).json() == rejected.json()
    for path in [gp, ap]:
        for method in ["PATCH", "DELETE"]:
            assert mysql_client.request(method, path, headers=key, json={}).status_code == 405
    assert mysql_client.get("/api/v1/activity-generations/" + str(uuid4()), headers=key).status_code == 404
    assert mysql_client.get("/api/v1/activities/" + str(uuid4()), headers=key).status_code == 404


def test_approved_activity_still_denies_other_learner(mysql_client, role_headers, planning):
    generation, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Synthetic review"}).status_code == 200
    for activity in generation["activities"]:
        assert mysql_client.get("/api/v1/activities/" + activity["id"], headers=role_headers["learner2"]).status_code == 404


def test_concurrent_generation_is_one_atomic_sequence(mysql_client, mysql_engine, role_headers, planning):
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(pp + "/generations", headers=role_headers["learner"], json={}), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 200, 201]
    assert all(r.json() == replies[0].json() for r in replies)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 1
        assert conn.scalar(select(func.count()).select_from(Activity)) == 2


def test_generation_activity_insert_failure_rolls_back(mysql_client, mysql_engine, role_headers, planning):
    route, payload, _, ep, _ = planning
    key = role_headers["learner"]
    _, pp = create(mysql_client, key, route, payload)
    before = mysql_client.get(ep + "/state", headers=key).json()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO activities"):
            raise OperationalError("private SQL", {}, Exception("private content"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        reply = mysql_client.post(pp + "/generations", headers=key, json={})
        assert reply.status_code == 503 and reply.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 0
        assert conn.scalar(select(func.count()).select_from(Activity)) == 0
    assert mysql_client.get(ep + "/state", headers=key).json() == before


def test_invalid_adapter_output_leaves_no_generation(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    import app.activities as api
    original = api.build_sequence
    def invalid(snapshot, decision):
        values = original(snapshot, decision).model_dump(mode="json")
        values["steps"].reverse()
        return values
    monkeypatch.setattr(api, "build_sequence", invalid)
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    assert mysql_client.post(pp + "/generations", headers=role_headers["learner"], json={}).status_code == 409
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 0
        assert conn.scalar(select(func.count()).select_from(Activity)) == 0


def test_hash_mismatch_cannot_be_approved_or_delivered(mysql_client, mysql_engine, role_headers, planning):
    generation, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).values(content_hash="0" * 64))
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Invalid"}).status_code == 409
    assert mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).status_code == 409
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(ActivityGeneration.review_status)) == "draft"


def test_archival_blocks_new_generation_and_retains_retry_reads(mysql_client, headers, role_headers, planning):
    generation, gp, plan, pilot, _ = generated(mysql_client, role_headers["learner"], planning)
    route, payload, _, _, _ = planning
    _, second = create(mysql_client, role_headers["learner"], route, {**payload, "time_budget_minutes": 26})
    assert mysql_client.post(pilot[1] + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(second + "/generations", headers=role_headers["learner"], json={}).status_code == 409
    retry = mysql_client.post("/api/v1/loop-plans/" + plan["id"] + "/generations", headers=role_headers["learner"], json={})
    assert retry.status_code == 200 and retry.json() == generation
    assert mysql_client.get(gp, headers=role_headers["learner"]).json() == generation


def test_generation_database_lineage_and_review_constraints(mysql_client, mysql_engine, role_headers, planning):
    generated(mysql_client, role_headers["learner"], planning)
    for statement, error in [
        (update(Activity).values(position=0), OperationalError),
        (update(Activity).values(position=99), IntegrityError),
        (update(Activity).values(loop_plan_id=str(uuid4())), IntegrityError),
        (update(Activity).values(generation_id=str(uuid4())), IntegrityError),
        (update(ActivityGeneration).values(review_status="approved"), OperationalError),
        (update(ActivityGeneration).values(loop_plan_id=str(uuid4())), IntegrityError),
    ]:
        with mysql_engine.connect() as conn:
            with pytest.raises(error): conn.execute(statement)
            conn.rollback()


def test_concurrent_conflicting_reviews_have_one_terminal_decision(mysql_client, role_headers, planning):
    _, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda decision: mysql_client.post(gp + "/review", headers=role_headers["instructor"],
                            json={"decision": decision, "note": "Synthetic decision"}), ["approved", "rejected"]))
    assert sorted(r.status_code for r in replies) == [200, 409]
    stored = mysql_client.get(gp, headers=role_headers["learner"]).json()
    assert stored["review_status"] == next(r.json()["review_status"] for r in replies if r.status_code == 200)
    assert stored["reviewed_at"].endswith("Z")


def test_review_write_failure_preserves_draft(mysql_client, mysql_engine, role_headers, planning):
    generation, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE activity_generations"):
            raise OperationalError("private statement", {}, Exception("private note"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        reply = mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Synthetic"})
        assert reply.status_code == 503 and reply.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(gp, headers=role_headers["learner"]).json() == generation


def test_multirole_principal_cannot_review_own_generation(mysql_client, role_headers, planning):
    from app.main import app
    from app.activities import require_instructor
    from app.identity import Principal, Role
    _, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    app.dependency_overrides[require_instructor] = lambda: Principal("other-learner", frozenset({Role.learner, Role.instructor}))
    try:
        assert mysql_client.post(gp + "/review", headers=role_headers["learner"], json={"decision": "approved", "note": "Self"}).status_code == 403
    finally:
        app.dependency_overrides.pop(require_instructor)


def test_unsupported_target_leaves_no_generation(mysql_client, mysql_engine, role_headers, planning):
    route, payload, pilot, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, {**payload, "target_skill_id": pilot[4][0]["id"]})
    reply = mysql_client.post(pp + "/generations", headers=role_headers["learner"], json={})
    assert reply.status_code == 409 and "DEBUGGING" in reply.json()["detail"]
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 0


def test_corrupted_approved_content_is_withheld(mysql_client, mysql_engine, role_headers, planning):
    generation, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Synthetic"}).status_code == 200
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).values(content_hash="0" * 64))
    assert mysql_client.get("/api/v1/activities/" + generation["activities"][0]["id"], headers=role_headers["learner"]).status_code == 409
