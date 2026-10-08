"""Demonstrate Track A fixtures; optionally plan over a retained published pilot via HTTP."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.planner import build_plan
from app.planner_fixtures import synthetic_input
from app.planner_schemas import PlannerInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", type=UUID)
    parser.add_argument("--domain-version-id", type=UUID)
    args = parser.parse_args()
    if bool(args.course_id) != bool(args.domain_version_id):
        parser.error("Provide both --course-id and --domain-version-id for the HTTP demo")
    for profile in ["unknown", "beginner", "experienced"]:
        fixture = synthetic_input(profile)
        plan = build_plan(fixture)
        assert plan == build_plan(fixture)
        focus = next(s.code for s in fixture.skills if s.id == str(plan.focus_skill_id))
        print("{}: focus={}, action={}, support={}, minutes={}/{}; steps={}".format(
            profile, focus, plan.action, plan.support_level, plan.estimated_minutes, plan.time_budget_minutes,
            ", ".join(s.role for s in plan.steps)))
    print("Internal evidence fixtures only; these bands are never written to live learner records.")
    if not args.course_id:
        return
    values = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    learners = [p for p in json.loads(values.get("DEV_PRINCIPALS", "[]")) if p["roles"] == ["learner"]]
    if len(learners) < 2:
        raise SystemExit("Configure two synthetic learner credentials for the isolation demo.")
    key, other_key, author_key = learners[0]["api_key"], learners[1]["api_key"], values["API_KEY"]

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

    def all_items(route, credential=key):
        result, offset = [], 0
        while True:
            page = request("GET", route + "?limit=100&offset=" + str(offset), [200], credential)["items"]
            result.extend(page)
            if len(page) < 100:
                return result
            offset += 100

    dp = "/api/v1/courses/{}/domain-versions/{}".format(args.course_id, args.domain_version_id)
    skills = all_items(dp + "/skills", author_key)
    target = next((s for s in skills if s["code"] == "DEBUGGING"), None)
    if target is None:
        raise SystemExit("This demo expects the published synthetic DEBUGGING target.")
    activities = all_items("/api/v1/catalog/activities")
    whole = next((a for a in activities if a["activity_type"] == "worked_example"
                  and {"learning_tasks", "supportive_information", "procedural_information"} <= {m["component"] for m in a["mappings"]}
                  and any(b["activity_type"] == "constructed_response" and "learning_tasks" in {m["component"] for m in b["mappings"]}
                          and all(a[p] == b[p] for p in ["learning_science_policy_id", "safety_policy_id"]) for b in activities)), None)
    if whole is None:
        raise SystemExit("Run the Day 6 catalog demo first to provide reviewed compatible activities.")
    learner = request("POST", "/api/v1/learners", [200, 201], payload={})
    lp = "/api/v1/learners/" + learner["id"]
    enrollment = request("POST", lp + "/enrollments", [200, 201], payload={
        "course_id": str(args.course_id), "domain_version_id": str(args.domain_version_id)})
    state_path = lp + "/enrollments/" + enrollment["id"] + "/state"
    before = all_items(state_path)
    payload = {"enrollment_id": enrollment["id"], "target_skill_id": target["id"], "time_budget_minutes": 25,
               "learning_science_policy_id": whole["learning_science_policy_id"], "safety_policy_id": whole["safety_policy_id"]}
    plan = request("POST", lp + "/loop-plans", [200, 201], payload=payload)
    path = "/api/v1/loop-plans/" + plan["id"]
    assert request("GET", path, [200]) == plan
    assert request("POST", lp + "/loop-plans", [200], payload=payload) == plan
    assert build_plan(PlannerInput(**plan["input_snapshot"])).model_dump(mode="json") == plan["decision"]
    request("GET", path, [404], other_key)
    request("POST", lp + "/loop-plans", [404], other_key, payload)
    request("GET", path, [403], author_key)
    request("POST", lp + "/loop-plans", [409], payload={**payload, "time_budget_minutes": 1})
    assert all_items(state_path) == before
    print("Saved plan: " + plan["id"])
    print("Verified stored-state planning, identical retries, snapshot replay, isolation, budget rejection and unchanged learner state.")


if __name__ == "__main__":
    main()
