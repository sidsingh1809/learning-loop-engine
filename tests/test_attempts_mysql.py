from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import Activity, ActivityGeneration, Attempt, AttemptScore, Evidence, LoopPlan, LoopStep
from app.planner import build_plan, canonical_snapshot
from app.planner_schemas import PlannerInput
from tests.test_catalog_mysql import policies
from tests.test_domains_mysql import create
from tests.test_generation_mysql import generated
from tests.test_plans_mysql import planning

pytestmark = pytest.mark.mysql


def answer(text="Repair: total += sale; trace 4, 4, 7. Explain accumulation.", key=None):
    return {"idempotency_key": key or str(uuid4()), "response": {"activity_type": "constructed_response", "text": text}}


@pytest.fixture
def ready(mysql_client, role_headers, planning):
    generation, gp, plan, pilot, ep = generated(mysql_client, role_headers["learner"], planning)
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"],
                             json={"decision": "approved", "note": "Synthetic content review"}).status_code == 200
    ap = "/api/v1/activities/" + generation["activities"][-1]["id"]
    return ap, generation, gp, plan, pilot, ep


def review_payload(client, path, instructor):
    content = client.get(path + "/review-content", headers=instructor)
    assert content.status_code == 200, content.text
    return {"criteria": [{"code": c["code"], "points": c["max_points"]} for c in content.json()["step"]["rubric"]["criteria"]],
            "note": "Programmatic synthetic scoring only; no expert approval."}


def test_written_attempt_review_evidence_and_state_application(mysql_client, mysql_engine, role_headers, ready):
    ap, _, _, plan, _, ep = ready
    learner, instructor = role_headers["learner"], role_headers["instructor"]
    before = mysql_client.get(ep + "/state", headers=learner).json()
    payload = answer()
    attempt, path = create(mysql_client, learner, ap + "/attempts", payload)
    assert attempt["status"] == "pending_review" and attempt["score"] is None
    assert attempt["created_at"].endswith("Z") and "submitted_by" not in attempt
    assert mysql_client.get(path, headers=learner).json() == attempt
    assert mysql_client.post(ap + "/attempts", headers=learner, json=payload).json() == attempt
    assert mysql_client.get(ap + "/attempts", headers=learner).json()["items"] == [attempt]
    scoring = review_payload(mysql_client, path, instructor)
    scoring["criteria"][0]["points"] = 1  # partial credit, not binary grading
    scored = mysql_client.post(path + "/review", headers=instructor, json=scoring)
    assert scored.status_code == 200, scored.text
    scored = scored.json()
    assert scored["status"] == "scored"
    assert scored["score"]["scorer_version"] == "instructor-rubric-v1"
    assert scored["score"]["reviewed_by"] == "other-instructor"
    assert scored["score"]["created_at"].endswith("Z")
    evidence = scored["score"]["evidence"]
    assert {e["skill_id"] for e in evidence} == {plan["decision"]["target_skill_id"], plan["decision"]["focus_skill_id"]}
    assert all(e["evidence_kind"] == "whole_task" and e["formal_certification"] is False for e in evidence)
    assert "expected_response" not in str(scored) and "correct_choice_id" not in str(scored)
    assert mysql_client.get(path, headers=learner).json() == scored
    assert mysql_client.post(ap + "/attempts", headers=learner, json=payload).json() == scored
    reversed_review = {**scoring, "criteria": list(reversed(scoring["criteria"]))}
    assert mysql_client.post(path + "/review", headers=instructor, json=reversed_review).json() == scored
    assert mysql_client.post(path + "/review", headers=instructor, json={**scoring, "note": "Changed"}).status_code == 409
    changed = {**scoring, "criteria": [{**c, "points": 0} for c in scoring["criteria"]]}
    assert mysql_client.post(path + "/review", headers=instructor, json=changed).status_code == 409
    after = mysql_client.get(ep + "/state", headers=learner).json()
    changed = [s for s in after["items"] if s["revision"]]
    assert len(changed) == 2 and all(s["band"] == "developing" and s["revision"] == 1 for s in changed)
    assert scored["state_application"]["policy_version"] == "provisional-mastery-v1"
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Attempt)) == 1
        assert conn.scalar(select(func.count()).select_from(AttemptScore)) == 1
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 2


def test_attempt_isolation_conflicts_and_immutable_surface(mysql_client, role_headers, ready):
    ap, generation, _, _, _, _ = ready
    learner = role_headers["learner"]
    payload = answer()
    attempt, path = create(mysql_client, learner, ap + "/attempts", payload)
    spoofed = {**role_headers["learner2"], "X-Subject": "other-learner", "X-Role": "instructor"}
    for method, target, body in [("GET", path, None), ("GET", ap + "/attempts", None), ("POST", ap + "/attempts", payload)]:
        assert mysql_client.request(method, target, headers=spoofed, json=body).status_code == 404
    assert mysql_client.get(path + "/review-content", headers=learner).status_code == 403
    assert mysql_client.post(path + "/review", headers=learner, json={"criteria": [{"code": "TARGET", "points": 2}], "note": "Spoof"}).status_code == 403
    assert mysql_client.post(ap + "/attempts", headers=learner, json=answer("Different", payload["idempotency_key"])).status_code == 409
    example = "/api/v1/activities/" + generation["activities"][0]["id"]
    assert mysql_client.post(example + "/attempts", headers=learner, json=payload).status_code == 409
    assert mysql_client.post(example + "/attempts", headers=learner, json=answer()).status_code == 409
    for method in ["PATCH", "DELETE"]:
        assert mysql_client.request(method, path, headers=learner, json={}).status_code == 405
    for target in ["/api/v1/attempts/" + str(uuid4()), "/api/v1/activities/" + str(uuid4()) + "/attempts"]:
        assert mysql_client.get(target, headers=learner).status_code == 404
    for query in ["limit=101", "offset=-1"]:
        assert mysql_client.get(ap + "/attempts?" + query, headers=learner).status_code == 422
    second, _ = create(mysql_client, learner, ap + "/attempts", answer())
    page = mysql_client.get(ap + "/attempts?limit=1&offset=1", headers=learner).json()
    assert len(page["items"]) == 1
    assert {a["id"] for a in mysql_client.get(ap + "/attempts", headers=learner).json()["items"]} == {attempt["id"], second["id"]}


@pytest.mark.parametrize("criteria", [
    [{"code": "TARGET", "points": 2}],
    [{"code": "TARGET", "points": 3}, {"code": "FOCUS", "points": 1}],
    [{"code": "TARGET", "points": 1}, {"code": "TARGET", "points": 1}],
    [{"code": "OTHER", "points": 1}, {"code": "FOCUS", "points": 1}],
])
def test_invalid_review_keeps_pending_without_evidence(mysql_client, mysql_engine, role_headers, ready, criteria):
    attempt, path = create(mysql_client, role_headers["learner"], ready[0] + "/attempts", answer())
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json={"criteria": criteria, "note": "Invalid"}).status_code == 422
    assert mysql_client.get(path, headers=role_headers["learner"]).json() == attempt
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(AttemptScore)) == 0
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 0


def test_draft_rejected_and_corrupted_content_block_submissions(mysql_client, mysql_engine, role_headers, planning):
    generation, gp, _, _, _ = generated(mysql_client, role_headers["learner"], planning)
    path = "/api/v1/activities/" + generation["activities"][-1]["id"] + "/attempts"
    assert mysql_client.post(path, headers=role_headers["learner"], json=answer()).status_code == 404
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).values(content_hash="0" * 64))
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "rejected", "note": "Synthetic"}).status_code == 200
    assert mysql_client.post(path, headers=role_headers["learner"], json=answer()).status_code == 404


def test_approved_corruption_and_response_mismatch_create_nothing(mysql_client, mysql_engine, role_headers, ready):
    path = ready[0] + "/attempts"
    wrong = {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "a"}}
    assert mysql_client.post(path, headers=role_headers["learner"], json=wrong).status_code == 422
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).values(content_hash="0" * 64))
    assert mysql_client.post(path, headers=role_headers["learner"], json=answer()).status_code == 409
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Attempt)) == 0


def test_archival_preserves_attempts_retries_and_pending_review(mysql_client, headers, role_headers, ready):
    ap, _, _, _, pilot, _ = ready
    payload = answer()
    attempt, path = create(mysql_client, role_headers["learner"], ap + "/attempts", payload)
    assert mysql_client.post(pilot[1] + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(ap + "/attempts", headers=role_headers["learner"], json=payload).json() == attempt
    assert mysql_client.post(ap + "/attempts", headers=role_headers["learner"], json=answer()).status_code == 409
    review = review_payload(mysql_client, path, role_headers["instructor"])
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).status_code == 200


def test_concurrent_submissions_and_reviews_are_single_records(mysql_client, mysql_engine, role_headers, ready):
    payload = answer()
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(ready[0] + "/attempts", headers=role_headers["learner"], json=payload), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 200, 201]
    assert all(r.json() == replies[0].json() for r in replies)
    path = replies[0].headers["location"]
    review = review_payload(mysql_client, path, role_headers["instructor"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review), range(3)))
    assert all(r.status_code == 200 and r.json() == replies[0].json() for r in replies)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Attempt)) == 1
        assert conn.scalar(select(func.count()).select_from(AttemptScore)) == 1
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 2


def test_concurrent_changed_submission_and_review_conflict(mysql_client, role_headers, ready):
    payload = answer()
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda text: mysql_client.post(ready[0] + "/attempts", headers=role_headers["learner"],
                            json=answer(text, payload["idempotency_key"])), ["One", "Two"]))
    assert sorted(r.status_code for r in replies) == [201, 409]
    path = next(r.headers["location"] for r in replies if r.status_code == 201)
    review = review_payload(mysql_client, path, role_headers["instructor"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda note: mysql_client.post(path + "/review", headers=role_headers["instructor"],
                              json={**review, "note": note}), ["One", "Two"]))
    assert sorted(r.status_code for r in replies) == [200, 409]


def test_multirole_cannot_review_own_attempt(mysql_client, role_headers, ready):
    from app.activities import require_instructor
    from app.identity import Principal, Role
    from app.main import app
    _, path = create(mysql_client, role_headers["learner"], ready[0] + "/attempts", answer())
    app.dependency_overrides[require_instructor] = lambda: Principal("other-learner", frozenset({Role.learner, Role.instructor}))
    try:
        assert mysql_client.get(path + "/review-content", headers=role_headers["learner"]).status_code == 403
        assert mysql_client.post(path + "/review", headers=role_headers["learner"],
            json={"criteria": [{"code": "TARGET", "points": 2}], "note": "Self"}).status_code == 403
    finally:
        app.dependency_overrides.pop(require_instructor)


def test_failed_review_rolls_back_score_and_all_evidence(mysql_client, mysql_engine, role_headers, ready):
    attempt, path = create(mysql_client, role_headers["learner"], ready[0] + "/attempts", answer())
    review = review_payload(mysql_client, path, role_headers["instructor"])
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO evidence"):
            raise OperationalError("private SQL", {}, Exception("private answer"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        result = mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review)
        assert result.status_code == 503 and result.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    assert mysql_client.get(path, headers=role_headers["learner"]).json() == attempt
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(AttemptScore)) == 0
        assert conn.scalar(select(func.count()).select_from(Evidence)) == 0


def beginner_generation(client, engine, key, planning):
    """Internal fixture only: persist a replayable plan; never modify learner state."""
    route, payload, _, _, _ = planning
    plan, _ = create(client, key, route, payload)
    values = plan["input_snapshot"]
    for state in values["states"]:
        state.update(band="developing", evidence_count=2, revision=1)
    snapshot = PlannerInput(**values)
    decision = build_plan(snapshot)
    with Session(engine) as session:
        row = LoopPlan(enrollment_id=plan["enrollment_id"], domain_version_id=plan["domain_version_id"],
            target_skill_id=str(decision.target_skill_id), focus_skill_id=str(decision.focus_skill_id),
            learning_science_policy_id=plan["learning_science_policy_id"], safety_policy_id=plan["safety_policy_id"],
            input_fingerprint=decision.input_fingerprint, time_budget_minutes=decision.time_budget_minutes,
            estimated_minutes=decision.estimated_minutes, input_snapshot=canonical_snapshot(snapshot),
            decision=decision.model_dump(mode="json", exclude={"steps"}),
            steps=[LoopStep(domain_version_id=plan["domain_version_id"], **s.model_dump(mode="json")) for s in decision.steps])
        session.add(row)
        session.commit()
        pp = "/api/v1/loop-plans/" + row.id
    generation, gp = create(client, key, pp + "/generations", {})
    return generation, gp


def test_selected_response_correct_incorrect_and_atomic_failure(mysql_client, mysql_engine, role_headers, planning):
    learner, instructor = role_headers["learner"], role_headers["instructor"]
    before = mysql_client.get(planning[3] + "/state", headers=learner).json()
    generation, gp = beginner_generation(mysql_client, mysql_engine, learner, planning)
    candidate = mysql_client.get(gp + "/review-content", headers=instructor).json()["candidate"]
    assert mysql_client.post(gp + "/review", headers=instructor, json={"decision": "approved", "note": "Internal synthetic fixture"}).status_code == 200
    activity = next(a for a in generation["activities"] if a["activity_type"] == "selected_response")
    step = next(s for s in candidate["steps"] if s["position"] == activity["position"])
    ap = "/api/v1/activities/" + activity["id"] + "/attempts"
    for choice in step["content"]["choices"]:
        payload = {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": choice["id"]}}
        attempt, path = create(mysql_client, learner, ap, payload)
        evidence = attempt["score"]["evidence"]
        assert len(evidence) == 1 and evidence[0]["evidence_kind"] == "part_task"
        assert evidence[0]["points"] == int(choice["id"] == step["content"]["correct_choice_id"])
        assert evidence[0]["skill_id"] == step["focus_skill_id"] != step["target_skill_id"]
        assert attempt["score"]["scorer_version"] == "selected-response-v1"
        assert attempt["score"]["reviewed_by"] is None
        assert "correct_choice_id" not in str(attempt) and "expected_response" not in str(attempt)
        assert mysql_client.post(ap, headers=learner, json=payload).json() == attempt
        assert mysql_client.get(path + "/review-content", headers=instructor).status_code == 409
        assert mysql_client.post(path + "/review", headers=instructor, json={"criteria": [{"code": "FOCUS", "points": 1}], "note": "Override"}).status_code == 409
    invalid = {"idempotency_key": str(uuid4()), "response": {"activity_type": "selected_response", "choice_id": "missing"}}
    assert mysql_client.post(ap, headers=learner, json=invalid).status_code == 422
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO evidence"):
            raise OperationalError("private SQL", {}, Exception("private"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        payload = {**invalid, "response": {**invalid["response"], "choice_id": "a"}}
        result = mysql_client.post(ap, headers=learner, json=payload)
        assert result.status_code == 503 and result.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    with mysql_engine.connect() as conn:
        for model in [Attempt, AttemptScore, Evidence]:
            assert conn.scalar(select(func.count()).select_from(model)) == 3
    after = mysql_client.get(planning[3] + "/state", headers=learner).json()
    changed = [s for s in after["items"] if s["revision"]]
    assert len(changed) == 1 and changed[0]["band"] == "developing"
    assert changed[0]["part_task_evidence_count"] == 3 and changed[0]["whole_task_attempt_count"] == 0


def test_mysql_evidence_bounds_and_lineage(mysql_client, mysql_engine, role_headers, ready):
    _, path = create(mysql_client, role_headers["learner"], ready[0] + "/attempts", answer())
    review = review_payload(mysql_client, path, role_headers["instructor"])
    assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=review).status_code == 200
    for statement, error in [
        (update(Evidence).values(points=-1), OperationalError),
        (update(Evidence).values(points=100), OperationalError),
        (update(Evidence).values(max_points=0), OperationalError),
        (update(Evidence).values(formal_certification=True), OperationalError),
        (update(Evidence).values(evidence_kind="certification"), OperationalError),
        (update(Evidence).values(skill_id=str(uuid4())), IntegrityError),
        (update(Evidence).values(domain_version_id=str(uuid4())), IntegrityError),
        (update(Attempt).values(activity_id=str(uuid4())), IntegrityError),
        (update(Attempt).values(enrollment_id=str(uuid4())), IntegrityError),
        (update(AttemptScore).values(reviewed_by=None), OperationalError),
    ]:
        with mysql_engine.connect() as conn:
            with pytest.raises(error):
                conn.execute(statement)
            conn.rollback()
