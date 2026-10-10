"""Demonstrate provisional state policy and optionally close a live synthetic loop."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.state_policy import STATE_POLICY_VERSION, advance_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", type=UUID)
    args = parser.parse_args()
    state = dict(band="unknown", evidence_count=0, revision=0, whole_task_evidence_count=0,
        part_task_evidence_count=0, whole_task_attempt_count=0, whole_task_points=0,
        whole_task_max_points=0, policy_version=None)
    print("Policy: " + STATE_POLICY_VERSION + " (synthetic, provisional)")
    for kind in ["part_task", "whole_task", "whole_task"]:
        state = advance_state(state, [SimpleNamespace(evidence_kind=kind, points=1, max_points=1)])
        print("{} success: {}, whole-task attempts {}, part-task criteria {}".format(
            kind, state["band"], state["whole_task_attempt_count"], state["part_task_evidence_count"]))
    if args.plan_id is None:
        print("Internal policy demonstration only. Add --plan-id to exercise the HTTP loop.")
        return
    values = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner_key = next(p["api_key"] for p in principals if p["roles"] == ["learner"])
    instructor_key = next(p["api_key"] for p in principals if p["roles"] == ["instructor"])

    def request(method, path, expected=(200,), credential=learner_key, payload=None):
        req = Request("http://127.0.0.1:8000" + path, method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"X-API-Key": credential, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as exc:
            status, result = exc.code, json.load(exc)
        assert status in expected, "{} {} returned {}, expected {}".format(method, path, status, expected)
        print("{} {} → {}".format(method, path, status))
        return result

    original = request("GET", "/api/v1/loop-plans/" + str(args.plan_id))
    learner = request("POST", "/api/v1/learners", (200, 201), payload={})
    ep = "/api/v1/learners/{}/enrollments/{}".format(learner["id"], original["enrollment_id"])
    sync = request("POST", ep + "/state/applications", payload={})
    print("Historical scores applied: {}".format(sync["applied_count"]))
    plan_request = dict(enrollment_id=original["enrollment_id"], target_skill_id=original["decision"]["target_skill_id"],
        learning_science_policy_id=original["learning_science_policy_id"], safety_policy_id=original["safety_policy_id"],
        time_budget_minutes=original["decision"]["time_budget_minutes"])
    route = "/api/v1/learners/" + learner["id"] + "/loop-plans"
    plan = request("POST", route, (200, 201), payload=plan_request)
    generation = request("POST", "/api/v1/loop-plans/" + plan["id"] + "/generations", (200, 201), payload={})
    gp = "/api/v1/activity-generations/" + generation["id"]
    if generation["review_status"] == "rejected":
        raise SystemExit("Saved generation is rejected; choose another plan.")
    candidate = request("GET", gp + "/review-content", credential=instructor_key)["candidate"]
    if generation["review_status"] == "draft":
        request("POST", gp + "/review", credential=instructor_key, payload={"decision": "approved",
            "note": "Synthetic Day 10 template inspection; expert and university review remain outstanding."})
    activity = next(a for a in generation["activities"] if a["activity_type"] == "constructed_response")
    step = next(s for s in candidate["steps"] if s["position"] == activity["position"])
    ap = "/api/v1/activities/" + activity["id"]
    request("GET", ap)
    before = request("GET", ep + "/state")
    payload = {"idempotency_key": str(uuid4()), "response": {"activity_type": "constructed_response",
        "text": "Replace total = sale with total += sale. Trace 4, 4, 7. Accumulate positive sales; zero and negative-only lists leave zero."}}
    attempt = request("POST", ap + "/attempts", (201,), payload=payload)
    path = "/api/v1/attempts/" + attempt["id"]
    assert attempt["score"] is None and attempt["state_application"] is None
    assert request("GET", ep + "/state") == before
    review = {"criteria": [{"code": c["code"], "points": c["max_points"]} for c in step["rubric"]["criteria"]],
        "note": "Synthetic Day 10 full-loop scoring demonstration; no expert or university approval."}
    scored = request("POST", path + "/review", credential=instructor_key, payload=review)
    after = request("GET", ep + "/state")
    assert after != before and scored["state_application"]["policy_version"] == STATE_POLICY_VERSION
    next_plan = request("POST", route, (201,), payload=plan_request)
    assert next_plan["id"] != plan["id"]
    assert request("POST", route, payload=plan_request) == next_plan
    assert request("POST", ap + "/attempts", payload=payload) == scored
    assert request("POST", path + "/review", credential=instructor_key, payload=review) == scored
    assert request("GET", ep + "/state") == after
    assert request("GET", "/api/v1/loop-plans/" + original["id"]) == original
    assert request("POST", ep + "/state/applications", payload={})["applied_count"] == 0
    for change in scored["state_application"]["changes"]:
        print("Skill {}: {} → {}; revision {} → {}".format(change["skill_id"], change["before"]["band"],
            change["after"]["band"], change["before"]["revision"], change["after"]["revision"]))
    print("Saved attempt: " + scored["id"])
    print("Next plan: " + next_plan["id"])
    print("Next decision: {}, focus {}".format(next_plan["decision"]["action"], next_plan["decision"]["focus_skill_id"]))
    print("Verified score → evidence → state → next plan, stable replay and immutable old snapshots.")


if __name__ == "__main__":
    main()
