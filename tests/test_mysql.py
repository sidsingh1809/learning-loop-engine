"""Integration tests run only against a disposable, explicitly named MySQL database."""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.mysql


def test_course_round_trip_and_duplicate_rejection(mysql_client, headers):
    payload = {"code": "cs101", "title": "Synthetic programming pilot", "description": "Practice 🧪"}
    created = mysql_client.post("/api/v1/courses", json=payload, headers=headers)
    assert created.status_code == 201
    course = created.json()
    assert course["code"] == "CS101"
    assert course["created_at"].endswith("Z")
    assert mysql_client.get(created.headers["location"], headers=headers).json() == course
    assert mysql_client.post("/api/v1/courses", json=payload, headers=headers).status_code == 409
    payload["code"] = "CS101"
    assert mysql_client.post("/api/v1/courses", json=payload, headers=headers).status_code == 409
    page = mysql_client.get("/api/v1/courses", headers=headers).json()
    assert page["items"] == [course]
    assert mysql_client.get("/health/ready").status_code == 200


def test_pagination_and_missing_course(mysql_client, headers):
    for code in ["CS103", "CS101", "CS102"]:
        assert mysql_client.post("/api/v1/courses", headers=headers, json={"code": code, "title": code}).status_code == 201
    response = mysql_client.get("/api/v1/courses?limit=1&offset=1", headers=headers)
    assert [item["code"] for item in response.json()["items"]] == ["CS102"]
    assert mysql_client.get("/api/v1/courses?limit=101", headers=headers).status_code == 422
    assert mysql_client.get("/api/v1/courses?offset=-1", headers=headers).status_code == 422
    assert mysql_client.get("/api/v1/courses/" + str(uuid4()), headers=headers).status_code == 404
    assert mysql_client.get("/api/v1/courses/not-a-uuid", headers=headers).status_code == 422


def test_edit_archive_and_retained_record(mysql_client, headers):
    created = mysql_client.post("/api/v1/courses", headers=headers,
                                json={"code": "life", "title": "Original", "description": "Keep this"})
    course = created.json()
    location = created.headers["location"]
    edited = mysql_client.patch(location, headers=headers, json={"title": " Revised ", "code": " life2 "})
    assert edited.status_code == 200
    edited = edited.json()
    assert (edited["title"], edited["code"], edited["description"]) == ("Revised", "LIFE2", "Keep this")
    assert edited["created_at"] == course["created_at"]
    assert edited["created_by"] == "dev-author"
    assert edited["updated_at"] >= course["updated_at"]
    assert edited["status"] == "active" and edited["archived_at"] is None
    assert mysql_client.get(location, headers=headers).json() == edited
    assert mysql_client.patch(location, headers=headers, json={"description": ""}).json()["description"] == ""

    archived = mysql_client.post(location + "/archive", headers=headers)
    assert archived.status_code == 200
    archived = archived.json()
    assert archived["id"] == course["id"] and archived["status"] == "archived"
    assert archived["archived_at"].endswith("Z")
    assert mysql_client.post(location + "/archive", headers=headers).json() == archived
    assert mysql_client.get(location, headers=headers).json() == archived
    assert mysql_client.get("/api/v1/courses", headers=headers).json()["items"] == []
    for status in ["archived", "all"]:
        assert mysql_client.get("/api/v1/courses?status=" + status, headers=headers).json()["items"] == [archived]
    assert mysql_client.patch(location, headers=headers, json={"title": "Overwrite"}).status_code == 409
    assert mysql_client.delete(location, headers=headers).status_code == 405
    assert mysql_client.post("/api/v1/courses", headers=headers, json={"code": "LIFE2", "title": "Reuse"}).status_code == 409
    assert mysql_client.get(location, headers=headers).json() == archived


def test_duplicate_edit_is_atomic(mysql_client, headers):
    for code in ["FIRST", "SECOND"]:
        created = mysql_client.post("/api/v1/courses", headers=headers, json={"code": code, "title": code})
    original = created.json()
    location = created.headers["location"]
    assert mysql_client.patch(location, headers=headers, json={"code": "first", "title": "Must roll back"}).status_code == 409
    assert mysql_client.get(location, headers=headers).json() == original


def test_other_author_denied_and_all_roles_can_read(mysql_client, headers, role_headers):
    created = mysql_client.post("/api/v1/courses", headers=headers, json={"code": "OWNED", "title": "Owned"})
    location = created.headers["location"]
    other = role_headers["author"]
    assert mysql_client.patch(location, headers=other, json={"title": "Take over"}).status_code == 403
    assert mysql_client.post(location + "/archive", headers=other).status_code == 403
    assert mysql_client.get(location, headers=headers).json() == created.json()
    for read_headers in role_headers.values():
        assert mysql_client.get(location, headers=read_headers).status_code == 200
        assert mysql_client.get("/api/v1/courses", headers=read_headers).status_code == 200
    other_created = mysql_client.post("/api/v1/courses", headers=other, json={"code": "OTHER", "title": "Other"})
    assert other_created.status_code == 201
    assert other_created.json()["created_by"] == "other-author"
    assert mysql_client.patch(other_created.headers["location"], headers=other, json={"title": "Edited"}).status_code == 200
    assert mysql_client.post(other_created.headers["location"] + "/archive", headers=other).status_code == 200


def test_lifecycle_missing_records_and_filter_validation(mysql_client, headers):
    location = "/api/v1/courses/" + str(uuid4())
    assert mysql_client.patch(location, headers=headers, json={"title": "Missing"}).status_code == 404
    assert mysql_client.post(location + "/archive", headers=headers).status_code == 404
    assert mysql_client.get("/api/v1/courses?status=invalid", headers=headers).status_code == 422
