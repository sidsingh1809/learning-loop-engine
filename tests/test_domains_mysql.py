from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.models import Competency, DomainVersion, Skill

pytestmark = pytest.mark.mysql


def create(client, headers, route, payload):
    response = client.post(route, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    assert client.get(response.headers["location"], headers=headers).json() == response.json()
    assert response.json()["created_at"].endswith("Z")
    return response.json(), response.headers["location"]


@pytest.fixture
def domain(mysql_client, headers):
    _, course = create(mysql_client, headers, "/api/v1/courses", {"code": "DOMAIN", "title": "Synthetic pilot"})
    version, path = create(mysql_client, headers, course + "/domain-versions", {})
    competency, cp = create(mysql_client, headers, path + "/competencies", {"code": " debug ", "statement": " Diagnose 🧪 "})
    return course, version, path, competency, cp


def skill_payload(competency, code="VARIABLES", **values):
    return {"competency_id": competency["id"], "code": code, "title": "Trace variables",
            "skill_kind": "routine", **values}


def test_five_skill_pilot_and_edits(mysql_client, headers, domain):
    course, version, path, competency, cp = domain
    assert version["version"] == 1 and version["status"] == "draft"
    assert competency["code"] == "DEBUG" and competency["statement"] == "Diagnose 🧪"
    created = []
    for code, kind in [("VARIABLES", "routine"), ("EXPRESSIONS", "routine"), ("CONDITIONALS", "routine"),
                       ("LOOPS", "routine"), ("DEBUGGING", "non_routine")]:
        item, location = create(mysql_client, headers, path + "/skills", skill_payload(competency, code.lower(), skill_kind=kind))
        created.append(item)
    assert len(mysql_client.get(path + "/skills", headers=headers).json()["items"]) == 5
    page = mysql_client.get(path + "/skills?limit=2&offset=1", headers=headers).json()
    assert [s["code"] for s in page["items"]] == ["DEBUGGING", "EXPRESSIONS"]
    edited = mysql_client.patch(location, headers=headers, json={"title": " Diagnose and fix ", "description": " Worked example "})
    assert edited.status_code == 200 and edited.json()["title"] == "Diagnose and fix"
    assert edited.json()["created_at"] == created[-1]["created_at"]
    assert mysql_client.get(location, headers=headers).json() == edited.json()
    assert mysql_client.patch(location, headers=headers, json={"description": ""}).json()["description"] == ""
    assert mysql_client.patch(cp, headers=headers, json={"statement": " Diagnose and fix a small program "}).json()["statement"] == "Diagnose and fix a small program"
    second, _ = create(mysql_client, headers, course + "/domain-versions", {})
    assert second["version"] == 2
    assert mysql_client.get(course + "/domain-versions?limit=1&offset=1", headers=headers).json()["items"] == [second]


def test_duplicate_codes_and_atomic_rollback(mysql_client, headers, domain):
    _, _, path, competency, cp = domain
    assert mysql_client.post(path + "/competencies", headers=headers, json={"code": "debug", "statement": "Duplicate"}).status_code == 409
    other, other_cp = create(mysql_client, headers, path + "/competencies", {"code": "OTHER", "statement": "Other"})
    assert mysql_client.patch(other_cp, headers=headers, json={"code": "debug", "statement": "Must roll back"}).status_code == 409
    assert mysql_client.get(other_cp, headers=headers).json() == other
    first, _ = create(mysql_client, headers, path + "/skills", skill_payload(competency))
    assert mysql_client.post(path + "/skills", headers=headers, json=skill_payload(other, "variables")).status_code == 409
    second, sp = create(mysql_client, headers, path + "/skills", skill_payload(other, "SECOND"))
    assert mysql_client.patch(sp, headers=headers, json={"code": "variables", "title": "Must roll back"}).status_code == 409
    assert mysql_client.get(sp, headers=headers).json() == second


def test_cross_version_and_course_scoping(mysql_client, headers, domain):
    course, version, path, competency, cp = domain
    skill, sp = create(mysql_client, headers, path + "/skills", skill_payload(competency))
    second, other_path = create(mysql_client, headers, course + "/domain-versions", {})
    assert mysql_client.get(other_path + "/skills", headers=headers).json()["items"] == []
    assert mysql_client.post(other_path + "/skills", headers=headers, json=skill_payload(competency)).status_code == 404
    for suffix, payload in [("/competencies/" + competency["id"], {"statement": "Wrong"}),
                            ("/skills/" + skill["id"], {"title": "Wrong"})]:
        assert mysql_client.get(other_path + suffix, headers=headers).status_code == 404
        assert mysql_client.patch(other_path + suffix, headers=headers, json=payload).status_code == 404
    _, other_course = create(mysql_client, headers, "/api/v1/courses", {"code": "OTHER", "title": "Other"})
    wrong = other_course + "/domain-versions/" + version["id"]
    assert mysql_client.get(wrong, headers=headers).status_code == 404
    assert mysql_client.post(wrong + "/competencies", headers=headers, json={"code": "NEW", "statement": "Wrong"}).status_code == 404
    # The same codes are valid in a different domain version.
    other_competency, _ = create(mysql_client, headers, other_path + "/competencies", {"code": "DEBUG", "statement": "Other version"})
    create(mysql_client, headers, other_path + "/skills", skill_payload(other_competency))


def test_ownership_archive_and_read_permissions(mysql_client, headers, role_headers, domain):
    course, _, path, competency, cp = domain
    skill, sp = create(mysql_client, headers, path + "/skills", skill_payload(competency))
    writes = [("POST", course + "/domain-versions", {}),
              ("POST", path + "/competencies", {"code": "NEW", "statement": "New"}),
              ("POST", path + "/skills", skill_payload(competency, "NEW")),
              ("PATCH", cp, {"statement": "Changed"}), ("PATCH", sp, {"title": "Changed"})]
    for method, route, payload in writes:
        assert mysql_client.request(method, route, headers=role_headers["author"], json=payload).status_code == 403
    assert mysql_client.post(course + "/archive", headers=headers).status_code == 200
    for method, route, payload in writes:
        assert mysql_client.request(method, route, headers=headers, json=payload).status_code == 409
    for read_headers in [headers, *role_headers.values()]:
        for route in [course + "/domain-versions", path, path + "/competencies", cp, path + "/skills", sp]:
            assert mysql_client.get(route, headers=read_headers).status_code == 200
    assert mysql_client.get(sp, headers=headers).json() == skill
    assert mysql_client.get(cp, headers=headers).json() == competency
    for route in [path, cp, sp]:
        assert mysql_client.delete(route, headers=headers).status_code == 405


def test_automaticity_patch_checks_resulting_state(mysql_client, headers, domain):
    _, _, path, competency, _ = domain
    original, sp = create(mysql_client, headers, path + "/skills", skill_payload(competency, requires_automaticity=True))
    assert mysql_client.patch(sp, headers=headers, json={"skill_kind": "non_routine"}).status_code == 422
    assert mysql_client.get(sp, headers=headers).json() == original
    result = mysql_client.patch(sp, headers=headers, json={"skill_kind": "non_routine", "requires_automaticity": False})
    assert result.status_code == 200
    assert mysql_client.patch(sp, headers=headers, json={"requires_automaticity": True}).status_code == 422
    assert mysql_client.get(sp, headers=headers).json() == result.json()


def test_missing_resources_and_pagination(mysql_client, headers, domain):
    course, _, path, competency, _ = domain
    assert mysql_client.get("/api/v1/courses/" + str(uuid4()) + "/domain-versions", headers=headers).status_code == 404
    assert mysql_client.post(course + "/domain-versions/" + str(uuid4()) + "/competencies", headers=headers,
                             json={"code": "NEW", "statement": "New"}).status_code == 404
    for resource in ["competencies", "skills"]:
        assert mysql_client.get(path + "/" + resource + "/" + str(uuid4()), headers=headers).status_code == 404
        for query in ["limit=101", "offset=-1", "limit=0"]:
            assert mysql_client.get(path + "/" + resource + "?" + query, headers=headers).status_code == 422
    assert mysql_client.get(path + "/skills/not-a-uuid", headers=headers).status_code == 422


def test_database_rejects_cross_version_skill(mysql_client, mysql_engine, headers, domain):
    course, _, _, competency, _ = domain
    second, _ = create(mysql_client, headers, course + "/domain-versions", {})
    with pytest.raises(IntegrityError):
        with mysql_engine.begin() as connection:
            connection.execute(insert(Skill).values(domain_version_id=second["id"], competency_id=competency["id"],
                                                    code="WRONG", title="Wrong", skill_kind="routine"))
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(Skill.id)) is None


def test_non_draft_domain_is_immutable(mysql_client, mysql_engine, headers, domain):
    _, version, path, competency, cp = domain
    _, sp = create(mysql_client, headers, path + "/skills", skill_payload(competency))
    assert mysql_client.post(path + "/publish", headers=headers, json={}).status_code == 200
    for method, route, payload in [
        ("POST", path + "/competencies", {"code": "NEW", "statement": "New"}),
        ("POST", path + "/skills", skill_payload(competency, "NEW")),
        ("PATCH", cp, {"statement": "Changed"}), ("PATCH", sp, {"title": "Changed"}),
    ]:
        assert mysql_client.request(method, route, headers=headers, json=payload).status_code == 409
    assert mysql_client.get(path, headers=headers).status_code == 200


def test_concurrent_version_allocation(mysql_client, headers, domain):
    course, _, _, _, _ = domain
    def post_version(_):
        return mysql_client.post(course + "/domain-versions", headers=headers, json={})
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(post_version, range(4)))
    assert [r.status_code for r in responses] == [201] * 4
    assert sorted(r.json()["version"] for r in responses) == [2, 3, 4, 5]
