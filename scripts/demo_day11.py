"""Show distinct templates, then optionally resume a retained sequence through HTTP."""
import argparse
from datetime import datetime, timezone
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
from app.review_schedule import REVIEW_INTERVAL, REVIEW_POLICY_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", type=UUID)
    args = parser.parse_args()
    snapshot = synthetic_input("beginner")
    plan = build_plan(snapshot)
    hashes = []
    for context in ["positive-sales-v1", "positive-donations-v1"]:
        sequence = build_sequence(snapshot, plan, context)
        hashes.append(content_hash(sequence))
        print("{}: {} connected activities, hash {}".format(context, len(sequence.steps), hashes[-1][:12]))
    assert hashes[0] != hashes[1]
    scored_at = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    print("{}: example score {} → review due {} (no mastery change)".format(
        REVIEW_POLICY_VERSION, scored_at.isoformat(), (scored_at + REVIEW_INTERVAL).isoformat()))
    if args.plan_id is None:
        print("Internal template/time example only. Add --plan-id for persisted HTTP continuity.")
        return
    values = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner_key = next(p["api_key"] for p in principals if p["roles"] == ["learner"])
    instructor_key = next(p["api_key"] for p in principals if p["roles"] == ["instructor"])

    def request(method, path, payload=None, credential=learner_key, expected=(200,)):
        req = Request("http://127.0.0.1:8000" + path, method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"X-API-Key": credential, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as exc:
            status, result = exc.code, json.load(exc)
        assert status in expected, "{} {} returned {}".format(method, path, status)
        print("{} {} → {}".format(method, path, status))
        return result

    original = request("GET", "/api/v1/loop-plans/" + str(args.plan_id))
    learner = request("POST", "/api/v1/learners", {}, expected=(200, 201))
    ep = "/api/v1/learners/{}/enrollments/{}".format(learner["id"], original["enrollment_id"])
    before = request("GET", ep + "/state")
    route = "/api/v1/loop-plans/" + str(args.plan_id) + "/generations"
    generations = []
    for context in ["positive-sales-v1", "positive-donations-v1"]:
        payload = {"context_variant": context}
        generation = request("POST", route, payload, expected=(200, 201))
        gp = "/api/v1/activity-generations/" + generation["id"]
        if generation["review_status"] == "draft":
            request("GET", gp + "/review-content", credential=instructor_key)
            generation = request("POST", gp + "/review", {"decision": "approved",
                "note": "Synthetic Day 11 context inspection; expert and university review remain outstanding."}, credential=instructor_key)
        assert generation["review_status"] == "approved", "Choose a plan whose context has not been rejected."
        assert request("POST", route, payload) == generation
        generations.append(generation)
    assert generations[0]["id"] != generations[1]["id"]
    assert generations[0]["content_hash"] != generations[1]["content_hash"]
    history = request("GET", route)
    assert {g["id"] for g in generations} <= {g["id"] for g in history["items"]}
    request("GET", ep + "/loop-plans")
    selected = generations[1]
    gp = "/api/v1/activity-generations/" + selected["id"]
    saved_progress = request("GET", gp + "/progress")
    support = next((a for a in selected["activities"] if a["activity_type"] == "worked_example"), None)
    if support:
        ap = "/api/v1/activities/" + support["id"]
        request("GET", ap)
        acknowledgment = request("POST", ap + "/completion", {}, expected=(200, 201))
        assert request("POST", ap + "/completion", {}) == acknowledgment
    resumed = request("GET", gp + "/progress")
    assert request("GET", gp + "/progress") == resumed
    assert resumed["generation_id"] == saved_progress["generation_id"]
    assert request("GET", ep + "/state") == before
    # Synchronize retained evidence to backfill reminders, without replaying state.
    sync = request("POST", ep + "/state/applications", {})
    assert sync["applied_count"] == 0, "Synchronize historical Day 9 evidence before using this continuity demo."
    upcoming = request("GET", ep + "/reviews?due_only=false")
    due = request("GET", ep + "/reviews")
    assert request("GET", ep + "/state") == before
    assert request("GET", "/api/v1/loop-plans/" + str(args.plan_id)) == original
    print("Resume generation: " + selected["id"])
    print("Progress: {}; next activity: {}".format(resumed["status"], resumed["next_activity_id"]))
    print("Scheduled skill reviews: {}; due now: {}".format(len(upcoming["items"]), len(due["items"])))
    print("Verified saved context, stable retries, durable acknowledgment and unchanged learner state.")


if __name__ == "__main__":
    main()
