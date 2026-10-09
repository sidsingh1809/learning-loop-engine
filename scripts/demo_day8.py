"""Demonstrate template fixtures; optionally generate/review/deliver a saved plan over HTTP."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.generator import build_sequence, content_hash
from app.planner import build_plan
from app.planner_fixtures import synthetic_input
from app.planner_schemas import DecisionRead, PlannerInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", type=UUID)
    args = parser.parse_args()
    for profile in ["unknown", "beginner", "experienced"]:
        snapshot = synthetic_input(profile)
        sequence = build_sequence(snapshot, build_plan(snapshot))
        assert sequence == build_sequence(snapshot, build_plan(snapshot))
        print("{}: {} minutes; {}; shared scenario={}, rubric={}".format(
            profile, sequence.estimated_minutes, " → ".join(s.role for s in sequence.steps),
            sequence.template_version, sequence.steps[-1].rubric.scoring_method))
    print("Internal evidence fixtures only; no bands, scores or state updates are written.")
    if args.plan_id is None:
        return
    values = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learners = [p for p in principals if p["roles"] == ["learner"]]
    instructor = next((p for p in principals if p["roles"] == ["instructor"]), None)
    if len(learners) < 2 or instructor is None:
        raise SystemExit("Configure two synthetic learner credentials and an instructor credential.")
    key, other_key, instructor_key = learners[0]["api_key"], learners[1]["api_key"], instructor["api_key"]

    def request(method, route, expected, credential=key, payload=None):
        req = Request("http://127.0.0.1:8000" + route, method=method,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={"X-API-Key": credential, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as exc:
            status, result = exc.code, json.load(exc)
        assert status in expected, "{} {} returned {}, expected {}".format(method, route, status, expected)
        print("{} {} → {}".format(method, route, status))
        return result

    pp = "/api/v1/loop-plans/" + str(args.plan_id)
    plan = request("GET", pp, [200])
    learner = request("POST", "/api/v1/learners", [200, 201], payload={})
    state_path = "/api/v1/learners/{}/enrollments/{}/state".format(learner["id"], plan["enrollment_id"])
    before = request("GET", state_path, [200])
    generation = request("POST", pp + "/generations", [200, 201], payload={})
    gp = "/api/v1/activity-generations/" + generation["id"]
    assert request("GET", gp, [200]) == generation
    assert request("POST", pp + "/generations", [200], payload={}) == generation
    request("GET", gp, [404], other_key)
    request("POST", pp + "/generations", [404], other_key, {})
    request("GET", gp + "/review-content", [403])
    request("POST", gp + "/review", [403], payload={"decision": "approved", "note": "Learner cannot review."})
    request("POST", pp + "/generations", [422], payload={"content": "Override"})
    ap = "/api/v1/activities/" + generation["activities"][0]["id"]
    if generation["review_status"] == "draft":
        request("GET", ap, [404])
    candidate = request("GET", gp + "/review-content", [200], instructor_key)["candidate"]
    sequence = build_sequence(PlannerInput(**plan["input_snapshot"]), DecisionRead(**plan["decision"]))
    assert candidate == sequence.model_dump(mode="json") and content_hash(sequence) == generation["content_hash"]
    if generation["review_status"] == "rejected":
        raise SystemExit("Retained candidate is rejected; delivery stays blocked. Create a revised plan/template for correction.")
    review_payload = {"decision": "approved", "note": "Programmatic synthetic template/rubric inspection only; expert and university review remain outstanding."}
    if generation["review_status"] == "draft":
        approved = request("POST", gp + "/review", [200], instructor_key, review_payload)
        assert request("POST", gp + "/review", [200], instructor_key, review_payload) == approved
    for activity in generation["activities"]:
        path = "/api/v1/activities/" + activity["id"]
        delivered = request("GET", path, [200])
        assert "expected_response" not in json.dumps(delivered) and "correct_choice_id" not in json.dumps(delivered)
        request("GET", path, [404], other_key)
    assert request("GET", state_path, [200]) == before
    print("Saved generation: " + generation["id"])
    print("Verified frozen sequence, review gate, retry/read, isolation, private scoring keys and unchanged learner state.")
    print("Development instructor review is synthetic only; no substantive university approval or learning efficacy is claimed.")


if __name__ == "__main__":
    main()
