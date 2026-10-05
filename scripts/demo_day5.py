"""Enroll two synthetic learners in a published domain and demonstrate isolation."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", type=UUID, required=True)
    parser.add_argument("--domain-version-id", type=UUID, required=True)
    args = parser.parse_args()
    values = dict(line.split("=", 1) for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learners = [p for p in principals if p["roles"] == ["learner"]][:2]
    if len(learners) != 2:
        raise SystemExit("Run scripts/init_local_env.py to configure two synthetic learner credentials.")

    def request(method, route, expected, key, payload=None, extra_headers=None):
        req = Request("http://127.0.0.1:8000" + route,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={"X-API-Key": key, "Content-Type": "application/json", **(extra_headers or {})}, method=method)
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as error:
            status, result = error.code, json.load(error)
        if status not in expected:
            raise SystemExit("{} {} returned {}, expected {}".format(method, route, status, expected))
        print("{} {} → {}".format(method, route, status))
        return result

    author_key = values["API_KEY"]
    domain_path = "/api/v1/courses/{}/domain-versions/{}".format(args.course_id, args.domain_version_id)
    assert request("GET", domain_path, [200], author_key)["status"] == "published"
    skills = request("GET", domain_path + "/skills?limit=100", [200], author_key)["items"]
    if len(skills) == 100:
        raise SystemExit("This synthetic demo supports domains with fewer than 100 skills.")
    enrolled = []
    payload = {"course_id": str(args.course_id), "domain_version_id": str(args.domain_version_id)}
    for principal in learners:
        key = principal["api_key"]
        learner = request("POST", "/api/v1/learners", [200, 201], key, {})
        assert set(learner) == {"id", "created_at"}
        lp = "/api/v1/learners/" + learner["id"]
        assert request("GET", lp, [200], key) == learner
        enrollment = request("POST", lp + "/enrollments", [200, 201], key, payload)
        ep = lp + "/enrollments/" + enrollment["id"]
        assert request("GET", ep, [200], key) == enrollment
        assert enrollment in request("GET", lp + "/enrollments", [200], key)["items"]
        state = request("GET", ep + "/state?limit=100", [200], key)
        assert {s["skill_id"] for s in state["items"]} == {s["id"] for s in skills}
        assert all(s["band"] == "unknown" and s["evidence_count"] == 0 and s["revision"] == 0 for s in state["items"])
        assert request("POST", lp + "/enrollments", [200], key, payload) == enrollment
        assert request("GET", ep + "/state?limit=100", [200], key) == state
        enrolled.append((principal, lp, ep))
    for own, other in [(enrolled[0], enrolled[1]), (enrolled[1], enrolled[0])]:
        key = own[0]["api_key"]
        spoof = {"X-Subject": other[0]["subject"], "X-Role": "instructor"}
        for route in [other[1], other[1] + "/enrollments", other[2], other[2] + "/state",
                      own[1] + "/enrollments/" + other[2].split("/")[-1] + "/state"]:
            request("GET", route, [404], key, extra_headers=spoof)
        request("POST", other[1] + "/enrollments", [404], key, payload)
    request("GET", enrolled[0][2] + "/state", [403], author_key)
    print("\nVerified two pseudonymous learners, {} unknown skills each, stable enrollment retries and mutual isolation.".format(len(skills)))
    print("Learner IDs: {} and {}".format(*(entry[1].split("/")[-1] for entry in enrolled)))


if __name__ == "__main__":
    main()
