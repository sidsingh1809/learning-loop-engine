from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import DomainVersion, SkillPrerequisite
from tests.test_domains_mysql import create, skill_payload

pytestmark = pytest.mark.mysql


@pytest.fixture
def graph(mysql_client, headers):
    _, course = create(mysql_client, headers, "/api/v1/courses", {"code": "GRAPH", "title": "Graph pilot"})
    version, path = create(mysql_client, headers, course + "/domain-versions", {})
    competency, cp = create(mysql_client, headers, path + "/competencies", {"code": "DEBUG", "statement": "Diagnose"})
    skills = [create(mysql_client, headers, path + "/skills", skill_payload(competency, code))[0]
              for code in ["A", "B", "C"]]
    return course, version, path, competency, cp, skills


def edge(dependent, prerequisite):
    return {"skill_id": dependent["id"], "prerequisite_skill_id": prerequisite["id"]}


def test_edges_cycle_rejection_removal_and_pagination(mysql_client, headers, graph):
    _, _, path, _, _, (a, b, c) = graph
    first, fp = create(mysql_client, headers, path + "/prerequisites", edge(b, a))
    second, _ = create(mysql_client, headers, path + "/prerequisites", edge(c, b))
    for payload, status in [(edge(a, a), 422), (edge(a, c), 409), (edge(a, b), 409), (edge(b, a), 409)]:
        assert mysql_client.post(path + "/prerequisites", headers=headers, json=payload).status_code == status
    items = mysql_client.get(path + "/prerequisites", headers=headers).json()["items"]
    ordered = sorted([first, second], key=lambda item: (item["skill_id"], item["prerequisite_skill_id"]))
    assert items == ordered
    assert mysql_client.get(path + "/prerequisites?limit=1&offset=1", headers=headers).json()["items"] == ordered[1:]
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert mysql_client.get(path + "/prerequisites?" + query, headers=headers).status_code == 422
    report = mysql_client.post(path + "/validate", headers=headers, json={}).json()
    assert report["valid"] and report["topological_skill_ids"] == [a["id"], b["id"], c["id"]]
    deleted = mysql_client.delete(fp, headers=headers)
    assert deleted.status_code == 204 and deleted.content == b""
    assert mysql_client.get(fp, headers=headers).status_code == 404
    assert mysql_client.delete(fp, headers=headers).status_code == 404
    create(mysql_client, headers, path + "/prerequisites", edge(a, c))


def test_edge_parent_isolation(mysql_client, headers, graph):
    course, version, path, _, _, (a, b, _) = graph
    first, _ = create(mysql_client, headers, path + "/prerequisites", edge(b, a))
    _, other = create(mysql_client, headers, course + "/domain-versions", {})
    competency, _ = create(mysql_client, headers, other + "/competencies", {"code": "OTHER", "statement": "Other"})
    foreign, _ = create(mysql_client, headers, other + "/skills", skill_payload(competency))
    for payload in [edge(a, foreign), edge(foreign, a), edge(a, {"id": str(uuid4())})]:
        assert mysql_client.post(path + "/prerequisites", headers=headers, json=payload).status_code == 404
    route = other + "/prerequisites/" + first["id"]
    assert mysql_client.get(route, headers=headers).status_code == 404
    assert mysql_client.delete(route, headers=headers).status_code == 404
    _, other_course = create(mysql_client, headers, "/api/v1/courses", {"code": "OTHER", "title": "Other"})
    wrong = other_course + "/domain-versions/" + version["id"]
    for action in ["validate", "publish"]:
        assert mysql_client.post(wrong + "/" + action, headers=headers, json={}).status_code == 404
        assert mysql_client.post(course + "/domain-versions/" + str(uuid4()) + "/" + action,
                                 headers=headers, json={}).status_code == 404
    assert mysql_client.get(wrong + "/prerequisites", headers=headers).status_code == 404
    assert mysql_client.post(wrong + "/prerequisites", headers=headers, json=edge(b, a)).status_code == 404


def test_incomplete_publish_preserves_draft(mysql_client, headers, graph):
    course, _, _, _, _, _ = graph
    draft, path = create(mysql_client, headers, course + "/domain-versions", {})
    report = mysql_client.post(path + "/validate", headers=headers, json={}).json()
    assert not report["valid"] and report["topological_skill_ids"] == []
    assert {issue["code"] for issue in report["issues"]} == {"no_competencies", "no_skills"}
    rejected = mysql_client.post(path + "/publish", headers=headers, json={})
    assert rejected.status_code == 422 and rejected.json()["detail"] == report
    assert mysql_client.get(path, headers=headers).json() == draft
    competency, _ = create(mysql_client, headers, path + "/competencies", {"code": "EMPTY", "statement": "Empty"})
    create(mysql_client, headers, path + "/competencies", {"code": "FILLED", "statement": "Filled"})
    create(mysql_client, headers, path + "/skills", skill_payload(competency))
    response = mysql_client.post(path + "/publish", headers=headers, json={})
    assert response.status_code == 422
    assert [i["code"] for i in response.json()["detail"]["issues"]] == ["empty_competencies"]
    assert mysql_client.get(path, headers=headers).json()["published_at"] is None


def test_publishing_immutability_reads_and_new_draft(mysql_client, headers, role_headers, graph):
    course, _, path, competency, cp, (a, b, _) = graph
    _, ep = create(mysql_client, headers, path + "/prerequisites", edge(b, a))
    published = mysql_client.post(path + "/publish", headers=headers, json={})
    assert published.status_code == 200
    assert published.json()["status"] == "published" and published.json()["published_at"].endswith("Z")
    assert mysql_client.get(path, headers=headers).json() == published.json()
    assert mysql_client.post(path + "/publish", headers=headers, json={}).json() == published.json()
    writes = [("POST", path + "/prerequisites", edge(a, b)), ("DELETE", ep, None),
              ("POST", path + "/skills", skill_payload(competency, "NEW")),
              ("POST", path + "/competencies", {"code": "NEW", "statement": "New"}),
              ("PATCH", path + "/skills/" + a["id"], {"title": "Changed"}),
              ("PATCH", cp, {"statement": "Changed"})]
    for method, route, payload in writes:
        assert mysql_client.request(method, route, headers=headers, json=payload).status_code == 409
    for key in [headers, *role_headers.values()]:
        assert mysql_client.get(ep, headers=key).status_code == 200
        assert mysql_client.post(path + "/validate", headers=key, json={}).json()["valid"]
    second, new_path = create(mysql_client, headers, course + "/domain-versions", {})
    assert second["status"] == "draft" and second["version"] == 2 and second["published_at"] is None
    assert mysql_client.get(new_path + "/skills", headers=headers).json()["items"] == []
    assert mysql_client.post(course + "/archive", headers=headers).status_code == 200
    assert mysql_client.post(path + "/publish", headers=headers, json={}).status_code == 409
    assert mysql_client.post(path + "/validate", headers=headers, json={}).json()["valid"]
    assert mysql_client.get(path, headers=headers).json() == published.json()


def test_graph_writes_enforce_owner_and_active_course(mysql_client, headers, role_headers, graph):
    course, _, path, _, _, (a, b, _) = graph
    _, ep = create(mysql_client, headers, path + "/prerequisites", edge(b, a))
    writes = [("POST", path + "/prerequisites", edge(a, b)), ("DELETE", ep, None), ("POST", path + "/publish", {})]
    for method, route, payload in writes:
        for role in role_headers:
            assert mysql_client.request(method, route, headers=role_headers[role], json=payload).status_code == 403
    assert mysql_client.post(course + "/archive", headers=headers).status_code == 200
    for method, route, payload in writes:
        assert mysql_client.request(method, route, headers=headers, json=payload).status_code == 409
    assert mysql_client.get(ep, headers=headers).status_code == 200


def test_db_constraints_and_publication_rechecks_cycle(mysql_client, mysql_engine, headers, graph):
    course, version, path, _, _, (a, b, c) = graph
    other, _ = create(mysql_client, headers, course + "/domain-versions", {})
    foreign_competency, _ = create(mysql_client, headers, course + "/domain-versions/" + other["id"] + "/competencies",
                                  {"code": "OTHER", "statement": "Other"})
    foreign, _ = create(mysql_client, headers, course + "/domain-versions/" + other["id"] + "/skills",
                        skill_payload(foreign_competency))
    for payload, error_type, code in [
        (dict(domain_version_id=other["id"], **edge(b, a)), IntegrityError, 1452),
        (dict(domain_version_id=version["id"], **edge(a, foreign)), IntegrityError, 1452),
        (dict(domain_version_id=version["id"], **edge(foreign, a)), IntegrityError, 1452),
        (dict(domain_version_id=version["id"], **edge(a, a)), OperationalError, 3819),
    ]:
        with pytest.raises(error_type) as error:
            with mysql_engine.begin() as connection:
                connection.execute(insert(SkillPrerequisite).values(**payload))
        assert error.value.orig.args[0] == code
    create(mysql_client, headers, path + "/prerequisites", edge(b, a))
    with pytest.raises(IntegrityError):
        with mysql_engine.begin() as connection:
            connection.execute(insert(SkillPrerequisite).values(domain_version_id=version["id"], **edge(b, a)))
    # Cycles are a service invariant: emulate an out-of-band write only in the test DB.
    with mysql_engine.begin() as connection:
        connection.execute(insert(SkillPrerequisite).values(domain_version_id=version["id"], **edge(c, b)))
        connection.execute(insert(SkillPrerequisite).values(domain_version_id=version["id"], **edge(a, c)))
    report = mysql_client.post(path + "/validate", headers=headers, json={}).json()
    assert not report["valid"] and report["issues"][0]["code"] == "invalid_graph"
    assert mysql_client.post(path + "/publish", headers=headers, json={}).status_code == 422
    with mysql_engine.connect() as connection:
        domain = connection.execute(select(DomainVersion.status, DomainVersion.published_at)
                                    .where(DomainVersion.id == version["id"])).one()
        assert domain == ("draft", None)


def simultaneous(*operations):
    gate = Barrier(len(operations))

    def run(operation):
        gate.wait(timeout=10)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        return list(executor.map(run, operations))


def test_simultaneous_opposing_edges_cannot_create_cycle(mysql_client, headers, graph):
    _, _, path, _, _, (a, b, _) = graph
    responses = simultaneous(
        lambda: mysql_client.post(path + "/prerequisites", headers=headers, json=edge(b, a)),
        lambda: mysql_client.post(path + "/prerequisites", headers=headers, json=edge(a, b)),
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(mysql_client.get(path + "/prerequisites", headers=headers).json()["items"]) == 1
    assert mysql_client.post(path + "/validate", headers=headers, json={}).json()["valid"]


def test_simultaneous_publish_and_edge_write(mysql_client, headers, graph):
    _, _, path, _, _, (a, b, _) = graph
    published, edited = simultaneous(
        lambda: mysql_client.post(path + "/publish", headers=headers, json={}),
        lambda: mysql_client.post(path + "/prerequisites", headers=headers, json=edge(b, a)),
    )
    assert published.status_code == 200 and edited.status_code in (201, 409)
    edges = mysql_client.get(path + "/prerequisites", headers=headers).json()["items"]
    assert len(edges) == (1 if edited.status_code == 201 else 0)
    assert mysql_client.post(path + "/prerequisites", headers=headers, json=edge(a, b)).status_code == 409
    assert mysql_client.post(path + "/validate", headers=headers, json={}).json()["valid"]


def test_simultaneous_publications_keep_one_timestamp(mysql_client, headers, graph):
    _, _, path, _, _, _ = graph
    responses = simultaneous(*[lambda: mysql_client.post(path + "/publish", headers=headers, json={}) for _ in range(3)])
    assert [r.status_code for r in responses] == [200] * 3
    assert all(response.json() == responses[0].json() for response in responses)
