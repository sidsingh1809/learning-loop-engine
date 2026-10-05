from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, func, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Enrollment, Learner, LearnerSkillState
from tests.test_domains_mysql import create, skill_payload

pytestmark = pytest.mark.mysql


@pytest.fixture
def pilot(mysql_client, headers):
    course, cp = create(mysql_client, headers, "/api/v1/courses", {"code": "LEARN", "title": "Synthetic learner pilot"})
    domain, dp = create(mysql_client, headers, cp + "/domain-versions", {})
    competency, _ = create(mysql_client, headers, dp + "/competencies", {"code": "DEBUG", "statement": "Debug"})
    skills = [create(mysql_client, headers, dp + "/skills", skill_payload(competency, code))[0]
              for code in ["VARIABLES", "EXPRESSIONS", "CONDITIONALS", "LOOPS", "DEBUGGING"]]
    assert mysql_client.post(dp + "/publish", headers=headers, json={}).status_code == 200
    return course, cp, domain, dp, skills


def enroll(client, key, pilot):
    learner, lp = create(client, key, "/api/v1/learners", {})
    course, _, domain, _, _ = pilot
    enrollment, ep = create(client, key, lp + "/enrollments",
                            {"course_id": course["id"], "domain_version_id": domain["id"]})
    return learner, lp, enrollment, ep


def test_two_learners_unknown_persisted_state_and_mutual_isolation(mysql_client, mysql_engine, role_headers, pilot):
    a = enroll(mysql_client, role_headers["learner"], pilot)
    b = enroll(mysql_client, role_headers["learner2"], pilot)
    assert a[0]["id"] != b[0]["id"]
    for own, other, role in [(a, b, "learner"), (b, a, "learner2")]:
        learner, lp, enrollment, ep = own
        key = role_headers[role]
        assert set(learner) == {"id", "created_at"}
        assert mysql_client.get(lp + "/enrollments", headers=key).json()["items"] == [enrollment]
        response = mysql_client.get(ep + "/state", headers=key)
        assert response.status_code == 200
        state = response.json()
        assert state["enrollment_id"] == enrollment["id"] and state["domain_version_id"] == pilot[2]["id"]
        assert [s["skill_id"] for s in state["items"]] == [s["id"] for s in sorted(pilot[4], key=lambda s: s["code"])]
        assert all(s["band"] == "unknown" and s["evidence_count"] == 0 and s["revision"] == 0
                   and s["updated_at"].endswith("Z") for s in state["items"])
        spoofed = {**key, "X-Subject": "second-learner" if role == "learner" else "other-learner",
                   "X-Learner-ID": other[0]["id"], "X-Role": "instructor"}
        for route in [other[1], other[1] + "/enrollments", other[3], other[3] + "/state", 
                      lp + "/enrollments/" + other[2]["id"], lp + "/enrollments/" + other[2]["id"] + "/state"]:
            assert mysql_client.get(route, headers=spoofed).status_code == 404
        assert mysql_client.post(other[1] + "/enrollments", headers=spoofed,
                                 json={"course_id": pilot[0]["id"], "domain_version_id": pilot[2]["id"]}).status_code == 404
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Learner)) == 2
        assert connection.scalar(select(func.count()).select_from(Enrollment)) == 2
        assert connection.scalar(select(func.count()).select_from(LearnerSkillState)) == 10


def test_registration_enrollment_retries_and_concurrency(mysql_client, mysql_engine, role_headers, pilot):
    key = role_headers["learner"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: mysql_client.post("/api/v1/learners", headers=key, json={}), range(3)))
    assert sorted(r.status_code for r in responses) == [200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    lp = responses[0].headers["location"]
    payload = {"course_id": pilot[0]["id"], "domain_version_id": pilot[2]["id"]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: mysql_client.post(lp + "/enrollments", headers=key, json=payload), range(3)))
    assert sorted(r.status_code for r in responses) == [200, 200, 201]
    assert all(r.json() == responses[0].json() for r in responses)
    ep = responses[0].headers["location"]
    before = mysql_client.get(ep + "/state", headers=key).json()
    assert mysql_client.post(lp + "/enrollments", headers=key, json=payload).status_code == 200
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(LearnerSkillState)) == 5


def test_enrollment_parent_scope_draft_archive_and_version_conflicts(mysql_client, headers, role_headers, pilot):
    key = role_headers["learner"]
    _, lp = create(mysql_client, key, "/api/v1/learners", {})
    course, cp, version, _, _ = pilot
    draft, dp = create(mysql_client, headers, cp + "/domain-versions", {})
    other, _ = create(mysql_client, headers, "/api/v1/courses", {"code": "OTHER", "title": "Other"})
    for cid, did, status in [(course["id"], draft["id"], 409), (other["id"], version["id"], 404),
                             (str(uuid4()), version["id"], 404), (course["id"], str(uuid4()), 404)]:
        assert mysql_client.post(lp + "/enrollments", headers=key,
                                 json={"course_id": cid, "domain_version_id": did}).status_code == status
    payload = {"course_id": course["id"], "domain_version_id": version["id"]}
    _, ep = create(mysql_client, key, lp + "/enrollments", payload)
    competency, _ = create(mysql_client, headers, dp + "/competencies", {"code": "NEW", "statement": "New"})
    create(mysql_client, headers, dp + "/skills", skill_payload(competency))
    assert mysql_client.post(dp + "/publish", headers=headers, json={}).status_code == 200
    assert mysql_client.post(lp + "/enrollments", headers=key,
                             json={**payload, "domain_version_id": draft["id"]}).status_code == 409
    before = mysql_client.get(ep + "/state", headers=key).json()
    assert mysql_client.post(cp + "/archive", headers=headers).status_code == 200
    _, other_lp = create(mysql_client, role_headers["learner2"], "/api/v1/learners", {})
    assert mysql_client.post(other_lp + "/enrollments", headers=role_headers["learner2"], json=payload).status_code == 409
    assert mysql_client.get(ep, headers=key).status_code == 200
    assert mysql_client.get(ep + "/state", headers=key).json() == before


def test_state_pagination_missing_records_and_no_writes(mysql_client, role_headers, pilot):
    key = role_headers["learner"]
    _, lp, _, ep = enroll(mysql_client, key, pilot)
    all_states = mysql_client.get(ep + "/state", headers=key).json()["items"]
    assert mysql_client.get(ep + "/state?limit=2&offset=1", headers=key).json()["items"] == all_states[1:3]
    assert mysql_client.get(ep + "/state?offset=100", headers=key).json()["items"] == []
    for query in ["limit=0", "limit=101", "offset=-1"]:
        for route in [lp + "/enrollments", ep + "/state"]:
            assert mysql_client.get(route + "?" + query, headers=key).status_code == 422
    assert mysql_client.get("/api/v1/learners/" + str(uuid4()), headers=key).status_code == 404
    assert mysql_client.get(lp + "/enrollments/" + str(uuid4()) + "/state", headers=key).status_code == 404
    assert mysql_client.get("/api/v1/learners/bad-uuid", headers=key).status_code == 422
    for method, route in [("PATCH", lp), ("DELETE", lp), ("PATCH", ep), ("DELETE", ep),
                           ("POST", ep + "/state"), ("PATCH", ep + "/state")]:
        assert mysql_client.request(method, route, headers=key, json={"band": "secure"}).status_code == 405


def test_enrollment_state_initialization_rolls_back_on_failure(mysql_client, mysql_engine, role_headers, pilot):
    key = role_headers["learner"]
    _, lp = create(mysql_client, key, "/api/v1/learners", {})
    def fail_state_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO learner_skill_states"):
            raise OperationalError("private statement", {}, Exception("private data"))
    event.listen(mysql_engine, "before_cursor_execute", fail_state_insert)
    try:
        response = mysql_client.post(lp + "/enrollments", headers=key,
                                     json={"course_id": pilot[0]["id"], "domain_version_id": pilot[2]["id"]})
        assert response.status_code == 503 and response.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail_state_insert)
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Enrollment)) == 0
        assert connection.scalar(select(func.count()).select_from(LearnerSkillState)) == 0


def test_enrollment_racing_publication_gets_every_published_skill(mysql_client, mysql_engine, headers, role_headers, pilot):
    from threading import Event, current_thread

    key = role_headers["learner"]
    _, lp = create(mysql_client, key, "/api/v1/learners", {})
    domain, dp = create(mysql_client, headers, pilot[1] + "/domain-versions", {})
    competency, _ = create(mysql_client, headers, dp + "/competencies", {"code": "NEW", "statement": "New"})
    first, _ = create(mysql_client, headers, dp + "/skills", skill_payload(competency, "FIRST"))
    paused, resume = Event(), Event()

    def pause_after_identity_read(conn, cursor, statement, parameters, context, executemany):
        if current_thread().name.startswith("enrollment-race") and "FROM courses" in statement and "FOR UPDATE" in statement:
            paused.set()
            assert resume.wait(10), "Publication did not finish before enrollment resumed"

    # Run the route directly in a worker with its own session; actual author HTTP
    # operations publish after the learner lookup has opened a repeatable-read snapshot.
    from fastapi import Response
    from sqlalchemy.orm import Session
    from app.identity import Principal, Role
    from app.learner_schemas import EnrollmentCreate
    from app.learners import create_enrollment
    from uuid import UUID

    def enroll_during_publish():
        with Session(mysql_engine, expire_on_commit=False) as session:
            return create_enrollment(UUID(lp.split("/")[-1]),
                                     EnrollmentCreate(course_id=pilot[0]["id"], domain_version_id=domain["id"]),
                                     Response(), Principal("other-learner", frozenset({Role.learner})), session).id

    event.listen(mysql_engine, "before_cursor_execute", pause_after_identity_read)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="enrollment-race") as pool:
            future = pool.submit(enroll_during_publish)
            try:
                assert paused.wait(5)
                last, _ = create(mysql_client, headers, dp + "/skills", skill_payload(competency, "LAST"))
                assert mysql_client.post(dp + "/publish", headers=headers, json={}).status_code == 200
            finally:
                resume.set()
            enrollment_id = future.result(timeout=5)
    finally:
        event.remove(mysql_engine, "before_cursor_execute", pause_after_identity_read)
    state = mysql_client.get(lp + "/enrollments/" + enrollment_id + "/state", headers=key).json()
    assert {item["skill_id"] for item in state["items"]} == {first["id"], last["id"]}


def test_database_rejects_cross_course_version_and_skill_state(mysql_client, mysql_engine, headers, role_headers, pilot):
    learner, _, enrollment, _ = enroll(mysql_client, role_headers["learner"], pilot)
    other, cp = create(mysql_client, headers, "/api/v1/courses", {"code": "OTHER", "title": "Other"})
    domain, dp = create(mysql_client, headers, cp + "/domain-versions", {})
    competency, _ = create(mysql_client, headers, dp + "/competencies", {"code": "OTHER", "statement": "Other"})
    skill, _ = create(mysql_client, headers, dp + "/skills", skill_payload(competency))
    invalid_inserts = [
        insert(Enrollment).values(learner_id=learner["id"], course_id=other["id"], domain_version_id=pilot[2]["id"]),
        insert(Enrollment).values(learner_id=learner["id"], course_id=pilot[0]["id"], domain_version_id=pilot[2]["id"]),
        insert(LearnerSkillState).values(enrollment_id=enrollment["id"], domain_version_id=pilot[2]["id"], skill_id=skill["id"]),
        insert(LearnerSkillState).values(enrollment_id=enrollment["id"], domain_version_id=domain["id"], skill_id=skill["id"]),
    ]
    for statement in invalid_inserts:
        with pytest.raises(IntegrityError):
            with mysql_engine.begin() as connection:
                connection.execute(statement)


def test_identity_subjects_are_case_sensitive(mysql_client, mysql_engine):
    with mysql_engine.begin() as connection:
        connection.execute(insert(Learner), [{"principal_subject": "Case"}, {"principal_subject": "case"}])
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Learner)) == 2


def test_roles_never_grant_other_learners_records(mysql_client, headers, role_headers, pilot):
    from app.identity import Principal, Role
    from app.main import app
    from app.security import require_api_key

    _, lp, _, ep = enroll(mysql_client, role_headers["learner"], pilot)
    for key in [headers, role_headers["author"], role_headers["instructor"], role_headers["integration"]]:
        for route in [lp, lp + "/enrollments", ep, ep + "/state"]:
            assert mysql_client.get(route, headers=key).status_code == 403
    # An additive author role can still only access this principal's own learner data.
    app.dependency_overrides[require_api_key] = lambda: Principal("second-learner", frozenset({Role.learner, Role.author}))
    try:
        for route in [lp, ep, ep + "/state"]:
            assert mysql_client.get(route).status_code == 404
        _, own = create(mysql_client, {}, "/api/v1/learners", {})
        assert mysql_client.get(own).status_code == 200
    finally:
        del app.dependency_overrides[require_api_key]
