"""Exercise the course API with synthetic data; never print local credentials."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        raise SystemExit("Run python3 scripts/init_local_env.py first.")
    values = dict(
        line.split("=", 1) for line in env_path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    base = "http://127.0.0.1:8000"
    headers = {"X-API-Key": values["API_KEY"], "Content-Type": "application/json"}
    payload = {
        "code": "CS101",
        "title": "Synthetic introductory programming pilot",
        "description": "Local demonstration data, not a university-approved course.",
    }
    request = Request(base + "/api/v1/courses", data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            course = json.load(response)
            print("Created synthetic course through POST /api/v1/courses (201).")
    except HTTPError as error:
        if error.code != 409:
            raise SystemExit("Course API returned HTTP {}".format(error.code)) from None
        # Page through the list so re-running remains safe even after more courses exist.
        offset = 0
        while True:
            request = Request(base + "/api/v1/courses?status=all&limit=100&offset=" + str(offset), headers=headers)
            with urlopen(request, timeout=10) as response:
                items = json.load(response)["items"]
            course = next((item for item in items if item["code"] == payload["code"]), None)
            if course:
                print("Reused existing CS101 course after expected duplicate response (409).")
                break
            if not items:
                raise SystemExit("Duplicate reported but CS101 could not be retrieved.")
            offset += len(items)
    request = Request(base + "/api/v1/courses/" + course["id"], headers=headers)
    with urlopen(request, timeout=10) as response:
        fetched = json.load(response)
    assert fetched == course
    print("Retrieved the same course through GET /api/v1/courses/{id} (200).")
    print(json.dumps(fetched, indent=2))


if __name__ == "__main__":
    main()
