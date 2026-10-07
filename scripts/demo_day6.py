"""Exercise synthetic catalog authoring, instructor-role review and approved-only reads."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    values = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    instructor = next((item for item in principals if item["roles"] == ["instructor"]), None)
    learner = next((item for item in principals if item["roles"] == ["learner"]), None)
    if instructor is None or learner is None:
        raise SystemExit("Configure synthetic instructor and learner credentials in DEV_PRINCIPALS first.")
    examples = json.loads((root / "app/synthetic_catalog.json").read_text())
    author_key, reviewer_key, learner_key = values["API_KEY"], instructor["api_key"], learner["api_key"]
    suffix = "_" + uuid4().hex[:8].upper()
    base = "/api/v1/catalog"
    approval = {"decision": "approved", "note": "Automated synthetic acceptance demonstration only; no university or expert approval claimed."}

    def request(method, route, expected, key, payload=None):
        req = Request("http://127.0.0.1:8000" + route,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={"X-API-Key": key, "Content-Type": "application/json"}, method=method)
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as error:
            status, result = error.code, json.load(error)
        if status != expected:
            raise SystemExit("{} {} returned {}, expected {}".format(method, route, status, expected))
        print("{} {} → {}".format(method, route, status))
        return result

    policies = {}
    for payload in examples["policies"]:
        payload = {**payload, "code": payload["code"] + suffix}
        item = request("POST", base + "/policy-versions", 201, author_key, payload)
        path = base + "/policy-versions/" + item["id"]
        request("GET", base + "/policies/" + item["id"], 404, learner_key)
        request("POST", path + "/review", 403, author_key, approval)
        approved = request("POST", path + "/review", 200, reviewer_key, approval)
        assert request("POST", path + "/review", 200, reviewer_key, approval) == approved
        policies[payload["category"]] = approved["id"]
    unapproved_policy = request("POST", base + "/policy-versions", 201, author_key,
                               {**examples["policies"][0], "code": "DRAFT_POLICY" + suffix})
    request("GET", base + "/policies/" + unapproved_policy["id"], 404, learner_key)

    approved_activities = []
    common = {"learning_science_policy_id": policies["learning_science"], "safety_policy_id": policies["safety"]}
    for payload in examples["activities"]:
        payload = {**payload, **common, "code": payload["code"] + suffix}
        item = request("POST", base + "/activity-versions", 201, author_key, payload)
        path = base + "/activity-versions/" + item["id"]
        request("GET", base + "/activities/" + item["id"], 404, learner_key)
        request("POST", path + "/review", 403, learner_key, approval)
        approved = request("POST", path + "/review", 200, reviewer_key, approval)
        assert approved["review_scope"] == "synthetic_only" and approved["evidence_tier"] == "provisional"
        assert request("GET", base + "/activities/" + item["id"], 200, learner_key) == approved
        request("PATCH", path, 405, author_key, {"title": "Changed"})
        request("POST", path + "/review", 409, reviewer_key, {"decision": "rejected", "note": "Change old approval"})
        approved_activities.append(approved)
    excluded = []
    for code, rejected in [("DRAFT_ACTIVITY", False), ("REJECTED_ACTIVITY", True)]:
        payload = {**examples["activities"][0], **common, "code": code + suffix}
        item = request("POST", base + "/activity-versions", 201, author_key, payload)
        if rejected:
            request("POST", base + "/activity-versions/" + item["id"] + "/review", 200,
                    reviewer_key, {"decision": "rejected", "note": "Synthetic rejection test; content requires revision."})
        request("GET", base + "/activities/" + item["id"], 404, learner_key)
        request("GET", base + "/activity-versions/" + item["id"], 403, learner_key)
        excluded.append(item["id"])
    payload = {**examples["activities"][0], **common, "code": "UNAPPROVED_POLICY" + suffix,
               "learning_science_policy_id": unapproved_policy["id"]}
    request("POST", base + "/activity-versions", 404, author_key, payload)
    all_items, offset = [], 0
    while True:
        items = request("GET", base + "/activities?limit=100&offset=" + str(offset), 200, learner_key)["items"]
        all_items.extend(items)
        if len(items) < 100:
            break
        offset += 100
    assert {item["id"] for item in approved_activities} <= {item["id"] for item in all_items}
    assert not set(excluded) & {item["id"] for item in all_items}
    assert {m["component"] for item in approved_activities for m in item["mappings"]} == {
        "learning_tasks", "supportive_information", "procedural_information", "part_task_practice"}
    print("\nVerified three approved activity formats, all four components, two approved pinned policies, and draft/rejected exclusion.")
    print("Synthetic run suffix: " + suffix)
    print("University and learning-science expert review remain outstanding. Planner and generation are later milestones.")


if __name__ == "__main__":
    main()
