"""Validate/publish the Day 3 pilot, or create a separate synthetic Day 4 pilot."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from demo_day3 import PILOT_SKILLS

PILOT_EDGES = [("EXPRESSIONS", "VARIABLES"), ("CONDITIONALS", "EXPRESSIONS"),
               ("LOOPS", "CONDITIONALS"), ("DEBUGGING", "LOOPS")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", type=UUID)
    parser.add_argument("--domain-version-id", type=UUID)
    args = parser.parse_args()
    if bool(args.course_id) != bool(args.domain_version_id):
        parser.error("Supply both parent IDs, or neither to create a new pilot")
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner = next((p for p in principals if p["roles"] == ["learner"]), None)
    if learner is None:
        raise SystemExit("Configure a learner-only development principal; run scripts/init_local_env.py.")
    author_key = values["API_KEY"]

    def request(method, route, expected, payload=None, key=author_key):
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

    if args.course_id:
        course_path = "/api/v1/courses/" + str(args.course_id)
        path = course_path + "/domain-versions/" + str(args.domain_version_id)
        course = request("GET", course_path, 200)
        version = request("GET", path, 200)
    else:
        course = request("POST", "/api/v1/courses", 201,
                         {"code": "DAY4-" + uuid4().hex[:12].upper(), "title": "Synthetic prerequisite pilot"})
        course_path = "/api/v1/courses/" + course["id"]
        version = request("POST", course_path + "/domain-versions", 201, {})
        path = course_path + "/domain-versions/" + version["id"]
        competency = request("POST", path + "/competencies", 201,
                             {"code": "DEBUG_PROGRAM", "statement": "Diagnose and fix a simple program."})
        for code, title, description, kind, automaticity in PILOT_SKILLS:
            request("POST", path + "/skills", 201,
                    {"competency_id": competency["id"], "code": code, "title": title,
                     "description": description, "skill_kind": kind, "requires_automaticity": automaticity})
    skills = {item["code"]: item for item in request("GET", path + "/skills?limit=100", 200)["items"]}
    required = {code for pair in PILOT_EDGES for code in pair}
    if not required.issubset(skills):
        raise SystemExit("This version does not contain the five Day 3 pilot skill codes.")
    existing = {(item["skill_id"], item["prerequisite_skill_id"]) for item in
                request("GET", path + "/prerequisites?limit=100", 200)["items"]}
    for dependent, prerequisite in PILOT_EDGES:
        candidate = (skills[dependent]["id"], skills[prerequisite]["id"])
        if candidate not in existing:
            request("POST", path + "/prerequisites", 201,
                    {"skill_id": candidate[0], "prerequisite_skill_id": candidate[1]})
    a, z = skills["VARIABLES"]["id"], skills["DEBUGGING"]["id"]
    request("POST", path + "/prerequisites", 422, {"skill_id": a, "prerequisite_skill_id": a})
    request("POST", path + "/prerequisites", 409, {"skill_id": a, "prerequisite_skill_id": z})
    report = request("POST", path + "/validate", 200, {})
    assert report["valid"], report["issues"]
    position = {skill_id: i for i, skill_id in enumerate(report["topological_skill_ids"])}
    for dependent, prerequisite in PILOT_EDGES:
        assert position[skills[prerequisite]["id"]] < position[skills[dependent]["id"]]
    request("POST", path + "/publish", 403, {}, key=learner["api_key"])
    published = request("POST", path + "/publish", 200, {})
    assert published["status"] == "published" and published["published_at"].endswith("Z")
    assert request("POST", path + "/publish", 200, {}) == published
    request("PATCH", path + "/skills/" + z, 409, {"title": "Blocked edit"})
    assert request("GET", path, 200) == published
    print("\nVerified published course {} ({})".format(course["code"], course["id"]))
    print("Domain {}: prerequisite graph validated; published content immutable.".format(version["id"]))
    print("Domain API: http://127.0.0.1:8000" + path)


if __name__ == "__main__":
    main()
