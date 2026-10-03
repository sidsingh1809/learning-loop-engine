"""Verify the Day 2 lifecycle through HTTP using a new synthetic course."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values = dict(
        line.split("=", 1) for line in env_path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner = next((p for p in principals if p["roles"] == ["learner"]), None)
    if learner is None:
        raise SystemExit("Configure a learner-only development principal in .env first; see docs/06-day-2.md.")
    author_key = values["API_KEY"]

    def request(method, route, expected, payload=None, key=author_key):
        req = Request(
            "http://127.0.0.1:8000" + route,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"X-API-Key": key, "Content-Type": "application/json"}, method=method,
        )
        try:
            with urlopen(req, timeout=10) as response:
                status, result = response.status, json.load(response)
        except HTTPError as error:
            status, result = error.code, json.load(error)
        if status != expected:
            raise SystemExit("{} {} returned {}, expected {}".format(method, route, status, expected))
        print("{} {} → {}".format(method, route, status))
        return result

    code = "DAY2-" + uuid4().hex[:12].upper()
    course = request("POST", "/api/v1/courses", 201, {"code": code, "title": "Synthetic Day 2 demo"})
    route = "/api/v1/courses/" + course["id"]
    edited = request("PATCH", route, 200, {"title": "Synthetic Day 2 demo — edited"})
    assert edited["title"] != course["title"] and edited["created_by"] == "dev-author"
    request("PATCH", route, 403, {"title": "Denied edit"}, key=learner["api_key"])
    request("POST", route + "/archive", 403, key=learner["api_key"])
    archived = request("POST", route + "/archive", 200)
    assert archived["status"] == "archived"
    assert request("POST", route + "/archive", 200) == archived
    assert request("GET", route, 200) == archived
    request("PATCH", route, 409, {"title": "Denied after archival"})
    request("DELETE", route, 405)
    request("POST", "/api/v1/courses", 409, {"code": code, "title": "Denied code reuse"})
    assert request("GET", route, 200) == archived
    print("Verified course {}: edited, archived, retained; learner writes denied.".format(code))


if __name__ == "__main__":
    main()
