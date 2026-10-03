"""Create a synthetic five-skill domain through HTTP; preserve it for Day 4."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


PILOT_SKILLS = [
    ("VARIABLES", "Trace variable values", "Track assignments and the current value of a variable.", "routine", True),
    ("EXPRESSIONS", "Evaluate simple expressions", "Apply arithmetic and comparison operators to predict a result.", "routine", True),
    ("CONDITIONALS", "Trace conditional branches", "Use a condition to identify which branch executes.", "routine", False),
    ("LOOPS", "Trace loop execution", "Follow iterations and determine when a loop terminates.", "routine", False),
    ("DEBUGGING", "Diagnose and fix a small program", "Combine tracing and test evidence to explain a defect and justify a repair.", "non_routine", False),
]


def main():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner = next((p for p in principals if p["roles"] == ["learner"]), None)
    if learner is None:
        raise SystemExit("Configure a learner-only development principal first; see docs/09-day-3.md.")
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

    code = "DAY3-" + uuid4().hex[:12].upper()
    course = request("POST", "/api/v1/courses", 201,
                     {"code": code, "title": "Synthetic introductory programming pilot",
                      "description": "Day 3 authoring example; provisional classifications, no real student data."})
    course_path = "/api/v1/courses/" + course["id"]
    version = request("POST", course_path + "/domain-versions", 201, {})
    path = course_path + "/domain-versions/" + version["id"]
    assert version["version"] == 1 and version["status"] == "draft"
    competency = request("POST", path + "/competencies", 201,
                         {"code": "DEBUG_PROGRAM", "statement": "Diagnose and fix a simple program using variables, conditionals, and loops."})
    created = []
    for skill_code, title, description, kind, automaticity in PILOT_SKILLS:
        skill = request("POST", path + "/skills", 201,
                        {"competency_id": competency["id"], "code": skill_code, "title": title,
                         "description": description, "skill_kind": kind, "requires_automaticity": automaticity})
        assert request("GET", path + "/skills/" + skill["id"], 200) == skill
        created.append(skill)
    skills = request("GET", path + "/skills", 200)["items"]
    assert skills == sorted(created, key=lambda skill: skill["code"])
    skill_path = path + "/skills/" + created[-1]["id"]
    edited = request("PATCH", skill_path, 200, {"description": "Explain the defect, justify a repair, and choose a test that checks the repair."})
    request("PATCH", skill_path, 403, {"title": "Denied learner edit"}, key=learner["api_key"])
    request("POST", course_path + "/domain-versions", 403, {}, key=learner["api_key"])
    request("POST", path + "/skills", 409,
            {"competency_id": competency["id"], "code": "variables", "title": "Duplicate", "skill_kind": "routine"})
    assert request("GET", skill_path, 200) == edited
    assert request("GET", path, 200) == version
    print("\nVerified active course {} ({})".format(code, course["id"]))
    print("Draft domain {}: one competency and five classified skills, ready for Day 4.".format(version["id"]))
    print("Domain API: http://127.0.0.1:8000" + path)


if __name__ == "__main__":
    main()
