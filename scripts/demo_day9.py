"""Verify provisional scoring fixtures and optionally submit/review a live saved plan."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.attempt_schemas import SelectedAnswer
from app.generator import build_sequence
from app.planner import build_plan
from app.planner_fixtures import synthetic_input
from app.scoring import selected_points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", type=UUID)
    args = parser.parse_args()
    snapshot = synthetic_input("beginner")
    steps = build_sequence(snapshot, build_plan(snapshot)).steps
    selected = next(s for s in steps if s.content.activity_type == "selected_response")
    for choice in selected.content.choices:
        result = selected_points(selected, SelectedAnswer(activity_type="selected_response", choice_id=choice.id))
        print("Internal selected-response fixture, choice {}: {}".format(choice.id, result))
    print("Selected-response fixture only; live learner state is unchanged.")
    if args.plan_id is None:
        return
    values = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learners = [p for p in principals if p["roles"] == ["learner"]]
    instructor = next(p for p in principals if p["roles"] == ["instructor"])
    key, other_key, instructor_key = learners[0]["api_key"], learners[1]["api_key"], instructor["api_key"]

    def request(method, path, expected, credential=key, payload=None):
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

    pp = "/api/v1/loop-plans/" + str(args.plan_id)
    plan = request("GET", pp, [200])
    learner = request("POST", "/api/v1/learners", [200, 201], payload={})
    state_path = "/api/v1/learners/{}/enrollments/{}/state".format(learner["id"], plan["enrollment_id"])
    before = request("GET", state_path, [200])
    generation = request("POST", pp + "/generations", [200, 201], payload={})
    gp = "/api/v1/activity-generations/" + generation["id"]
    candidate = request("GET", gp + "/review-content", [200], instructor_key)["candidate"]
    if generation["review_status"] == "rejected":
        raise SystemExit("This generation was rejected; use another saved plan.")
    if generation["review_status"] == "draft":
        request("POST", gp + "/review", [200], instructor_key, {
            "decision": "approved", "note": "Programmatic synthetic template inspection only; expert review remains outstanding."})
    activity = next(a for a in generation["activities"] if a["activity_type"] == "constructed_response")
    ap = "/api/v1/activities/" + activity["id"]
    step = next(s for s in candidate["steps"] if s["position"] == activity["position"])
    payload = {"idempotency_key": str(uuid4()), "response": {
        "activity_type": "constructed_response", "text": "Replace total = sale with total += sale. Trace: 4, 4, 7. Accumulate positive sales; zero and negative-only lists leave zero."}}
    attempt = request("POST", ap + "/attempts", [201], payload=payload)
    path = "/api/v1/attempts/" + attempt["id"]
    assert attempt["status"] == "pending_review" and attempt["score"] is None
    assert request("GET", path, [200]) == attempt
    assert request("POST", ap + "/attempts", [200], payload=payload) == attempt
    request("GET", path, [404], other_key)
    request("POST", ap + "/attempts", [404], other_key, payload)
    request("GET", path + "/review-content", [403])
    request("POST", ap + "/attempts", [422], payload={**payload, "score": 1})
    request("POST", ap + "/attempts", [409], payload={**payload, "response": {**payload["response"], "text": "Different response"}})
    review = {"criteria": [{"code": c["code"], "points": c["max_points"]} for c in step["rubric"]["criteria"]],
              "note": "Programmatic synthetic review/scoring demonstration only; no expert or university approval."}
    private = request("GET", path + "/review-content", [200], instructor_key)
    assert private["attempt"] == attempt
    scored = request("POST", path + "/review", [200], instructor_key, review)
    assert scored["status"] == "scored" and len(scored["score"]["evidence"]) == len(review["criteria"])
    assert all(e["evidence_kind"] == "whole_task" and e["formal_certification"] is False for e in scored["score"]["evidence"])
    assert request("POST", path + "/review", [200], instructor_key, review) == scored
    assert request("POST", ap + "/attempts", [200], payload=payload) == scored
    assert request("GET", path, [200]) == scored
    assert "expected_response" not in json.dumps(scored) and "correct_choice_id" not in json.dumps(scored)
    request("POST", path + "/review", [409], instructor_key, {**review, "note": "Changed terminal score"})
    assert any(a["id"] == attempt["id"] for a in request("GET", ap + "/attempts", [200])["items"])
    assert request("GET", state_path, [200]) != before
    assert scored["state_application"] is not None
    print("Saved attempt: " + attempt["id"])
    print("Verified immutable evidence, private rubric keys, retry/conflict handling and learner isolation.")
    print("Day 10 now applies scored evidence transactionally; no AI provider or real learner data was used.")


if __name__ == "__main__":
    main()
