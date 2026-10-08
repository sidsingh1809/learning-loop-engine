from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, func, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import LearnerSkillState, LoopPlan, LoopStep
from app.planner import build_plan
from app.planner_schemas import PlannerInput
from tests.test_catalog_mysql import policies, activity_payload, review
from tests.test_catalog_contract import ROOT
from tests.test_domains_mysql import create, skill_payload
from tests.test_learners_mysql import enroll

pytestmark = pytest.mark.mysql


@pytest.fixture
def planning(mysql_client, headers, role_headers, policies):
    course, cp = create(mysql_client, headers, "/api/v1/courses", {"code": "PLAN", "title": "Synthetic planning"})
    domain, dp = create(mysql_client, headers, cp + "/domain-versions", {})
    competency, _ = create(mysql_client, headers, dp + "/competencies", {"code": "DEBUG", "statement": "Debug a program"})
    foundation, _ = create(mysql_client, headers, dp + "/skills", skill_payload(competency, "VARIABLES", requires_automaticity=True))
    target, _ = create(mysql_client, headers, dp + "/skills", skill_payload(competency, "DEBUGGING", skill_kind="non_routine"))
    create(mysql_client, headers, dp + "/prerequisites", {"skill_id": target["id"], "prerequisite_skill_id": foundation["id"]})
    assert mysql_client.post(dp + "/publish", headers=headers, json={}).status_code == 200
    pilot = (course, cp, domain, dp, [foundation, target])
    _, lp, enrollment, ep = enroll(mysql_client, role_headers["learner"], pilot)
    activities = []
    for i in range(3):
        activity, path = create(mysql_client, headers, ROOT + "/activity-versions", activity_payload(policies, i))
        activities.append(review(mysql_client, role_headers["instructor"], path))
    payload = {"enrollment_id": enrollment["id"], "target_skill_id": target["id"], "time_budget_minutes": 25,
               "learning_science_policy_id": policies["learning_science"]["id"], "safety_policy_id": policies["safety"]["id"]}
    return lp + "/loop-plans", payload, pilot, ep, activities


def test_persisted_plan_repeat_read_replay_and_no_state_change(mysql_client, mysql_engine, role_headers, planning):
    route, payload, pilot, ep, activities = planning
    key = role_headers["learner"]
    before = mysql_client.get(ep + "/state", headers=key).json()
    plan, path = create(mysql_client, key, route, payload)
    decision = plan["decision"]
    assert decision["focus_skill_id"] == pilot[4][0]["id"]
    assert decision["target_skill_id"] == pilot[4][1]["id"]
    assert decision["action"] == "diagnostic_or_guided" and decision["estimated_minutes"] == 16
    assert decision == build_plan(PlannerInput(**plan["input_snapshot"])).model_dump(mode="json")
    again = mysql_client.post(route, headers=key, json=payload)
    assert again.status_code == 200 and again.json() == plan and again.headers["location"] == path
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(LoopPlan)) == 1
        assert conn.scalar(select(func.count()).select_from(LoopStep)) == 2
    # A new immutable version cannot rewrite an existing plan's snapshot or pins.
    assert mysql_client.get(path, headers=key).json() == plan
    assert {s["activity_variant_id"] for s in decision["steps"]} <= {a["id"] for a in activities}


def test_plan_isolation_parent_scope_and_retained_reads(mysql_client, headers, role_headers, planning):
    route, payload, pilot, _, _ = planning
    key = role_headers["learner"]
    plan, path = create(mysql_client, key, route, payload)
    _, other_lp, other_enrollment, _ = enroll(mysql_client, role_headers["learner2"], pilot)
    spoof = {**role_headers["learner2"], "X-Subject": "other-learner", "X-Role": "instructor"}
    assert mysql_client.get(path, headers=spoof).status_code == 404
    assert mysql_client.post(route, headers=spoof, json=payload).status_code == 404
    assert mysql_client.post(other_lp + "/loop-plans", headers=spoof, json=payload).status_code == 404
    assert mysql_client.post(route, headers=key, json={**payload, "enrollment_id": other_enrollment["id"]}).status_code == 404
    assert mysql_client.get("/api/v1/loop-plans/" + str(uuid4()), headers=key).status_code == 404
    for method in ["PATCH", "DELETE"]:
        assert mysql_client.request(method, path, headers=key, json={}).status_code == 405
    assert mysql_client.post(pilot[1] + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(route, headers=key, json=payload).status_code == 409
    assert mysql_client.get(path, headers=key).json() == plan


def test_planning_catalog_policy_and_budget_failures_leave_no_plan(mysql_client, mysql_engine, headers, role_headers, planning):
    route, payload, _, _, _ = planning
    key = role_headers["learner"]
    for changes, code in [({"target_skill_id": str(uuid4())}, 404), ({"time_budget_minutes": 15}, 409),
                          ({"learning_science_policy_id": str(uuid4())}, 404),
                          ({"learning_science_policy_id": payload["safety_policy_id"]}, 422)]:
        response = mysql_client.post(route, headers=key, json={**payload, **changes})
        assert response.status_code == code, response.text
        if code == 409: assert "16 minutes" in response.json()["detail"]
    from tests.test_catalog_contract import EXAMPLES
    draft, dp = create(mysql_client, headers, ROOT + "/policy-versions", {**EXAMPLES["policies"][0], "code": "OTHER"})
    assert mysql_client.post(route, headers=key, json={**payload, "learning_science_policy_id": draft["id"]}).status_code == 404
    approved = review(mysql_client, role_headers["instructor"], dp)
    assert mysql_client.post(route, headers=key, json={**payload, "learning_science_policy_id": approved["id"]}).status_code == 409
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(LoopPlan)) == 0
        assert conn.scalar(select(func.count()).select_from(LoopStep)) == 0


def test_same_input_concurrency_creates_one_plan(mysql_client, mysql_engine, role_headers, planning):
    route, payload, _, _, _ = planning
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: mysql_client.post(route, headers=role_headers["learner"], json=payload), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 200, 201]
    assert all(r.json() == replies[0].json() for r in replies)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(LoopPlan)) == 1


def test_plan_step_failure_rolls_back_entire_plan(mysql_client, mysql_engine, role_headers, planning):
    route, payload, _, ep, _ = planning
    key = role_headers["learner"]
    before = mysql_client.get(ep + "/state", headers=key).json()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO loop_steps"):
            raise OperationalError("private statement", {}, Exception("private input"))
    event.listen(mysql_engine, "before_cursor_execute", fail)
    try:
        reply = mysql_client.post(route, headers=key, json=payload)
        assert reply.status_code == 503 and reply.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(LoopPlan)) == 0
        assert conn.scalar(select(func.count()).select_from(LoopStep)) == 0
    assert mysql_client.get(ep + "/state", headers=key).json() == before


def test_plan_fk_duration_and_snapshot_pin_constraints(mysql_client, mysql_engine, role_headers, planning):
    route, payload, _, _, _ = planning
    plan, _ = create(mysql_client, role_headers["learner"], route, payload)
    from sqlalchemy import update
    for stmt, error in [
        (update(LoopPlan).values(estimated_minutes=26), OperationalError),
        (update(LoopPlan).values(target_skill_id=str(uuid4())), IntegrityError),
        (update(LoopPlan).values(domain_version_id=str(uuid4())), IntegrityError),
        (update(LoopStep).values(activity_variant_id=str(uuid4())), IntegrityError),
        (update(LoopStep).values(skill_id=str(uuid4())), IntegrityError),
        (update(LoopStep).values(position=0), OperationalError),
    ]:
        with pytest.raises(error):
            with mysql_engine.begin() as conn: conn.execute(stmt)
    assert mysql_client.get("/api/v1/loop-plans/" + plan["id"], headers=role_headers["learner"]).json() == plan
