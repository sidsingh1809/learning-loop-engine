from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import event, func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import ActivityVariant, ComponentActivityMapping, PolicyVersion
from tests.test_catalog_contract import EXAMPLES, ROOT
from tests.test_domains_mysql import create

pytestmark = pytest.mark.mysql
APPROVAL = {"decision": "approved", "note": "Reviewed for synthetic prototype use only; university review remains required."}


def review(client, key, path, payload=APPROVAL):
    response = client.post(path + "/review", headers=key, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def policies(mysql_client, headers, role_headers):
    result = {}
    for payload in EXAMPLES["policies"]:
        item, path = create(mysql_client, headers, ROOT + "/policy-versions", payload)
        result[payload["category"]] = review(mysql_client, role_headers["instructor"], path)
    return result


def activity_payload(policies, index=0):
    return {**deepcopy(EXAMPLES["activities"][index]),
            "learning_science_policy_id": policies["learning_science"]["id"],
            "safety_policy_id": policies["safety"]["id"]}


def test_approved_three_format_catalog_all_components_and_unapproved_exclusion(mysql_client, mysql_engine, headers, role_headers, policies):
    approved = []
    for index in range(3):
        item, path = create(mysql_client, headers, ROOT + "/activity-versions", activity_payload(policies, index))
        for role in role_headers.values():
            assert mysql_client.get(ROOT + "/activities/" + item["id"], headers=role).status_code == 404
        approved.append(review(mysql_client, role_headers["instructor"], path))
    payload = {**activity_payload(policies), "code": "DRAFT"}
    draft, _ = create(mysql_client, headers, ROOT + "/activity-versions", payload)
    rejected, rp = create(mysql_client, headers, ROOT + "/activity-versions", {**payload, "code": "REJECTED"})
    review(mysql_client, role_headers["instructor"], rp, {"decision": "rejected", "note": "Needs revision"})
    for key in [headers, *role_headers.values()]:
        items = mysql_client.get(ROOT + "/activities?status=draft&limit=100", headers=key).json()["items"]
        assert {item["id"] for item in items} == {item["id"] for item in approved}
        assert {item["activity_type"] for item in items} == {"worked_example", "selected_response", "constructed_response"}
        assert {m["component"] for item in items for m in item["mappings"]} == {
            "learning_tasks", "supportive_information", "procedural_information", "part_task_practice"}
        assert all(item["review_scope"] == "synthetic_only" and item["evidence_tier"] == "provisional"
                   and item["reviewed_at"].endswith("Z") for item in items)
        for item in [draft, rejected]:
            assert mysql_client.get(ROOT + "/activities/" + item["id"], headers=key).status_code == 404
        for item in approved:
            assert mysql_client.get(ROOT + "/activities/" + item["id"], headers=key).json() == item
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ActivityVariant)) == 5
        assert connection.scalar(select(func.count()).select_from(ComponentActivityMapping)) == 11


def test_policy_review_visibility_and_ownership(mysql_client, headers, role_headers):
    draft, path = create(mysql_client, headers, ROOT + "/policy-versions", EXAMPLES["policies"][0])
    assert mysql_client.get(ROOT + "/policies", headers=headers).json()["items"] == []
    assert mysql_client.get(ROOT + "/policies/" + draft["id"], headers=headers).status_code == 404
    assert mysql_client.get(path, headers=headers).json() == draft
    assert mysql_client.get(path, headers=role_headers["author"]).status_code == 404
    assert mysql_client.get(ROOT + "/policy-versions", headers=role_headers["author"]).json()["items"] == []
    assert mysql_client.get(path, headers=role_headers["instructor"]).json() == draft
    approved = review(mysql_client, role_headers["instructor"], path)
    assert mysql_client.get(ROOT + "/policies/" + draft["id"], headers=role_headers["learner"]).json() == approved
    draft2, p2 = create(mysql_client, headers, ROOT + "/policy-versions", {**EXAMPLES["policies"][0], "version": 2})
    assert mysql_client.get(ROOT + "/policies", headers=headers).json()["items"] == [approved]
    review(mysql_client, role_headers["instructor"], p2, {"decision": "rejected", "note": "Needs revision"})
    assert mysql_client.get(ROOT + "/policies/" + draft2["id"], headers=headers).status_code == 404
    for kind in ["policy", "activity"]:
        assert mysql_client.get(ROOT + "/" + kind + "-versions/" + str(uuid4()), headers=headers).status_code == 404


def test_review_retries_conflicts_and_self_review(mysql_client, headers, role_headers, policies):
    from app.identity import Principal, Role
    from app.main import app
    from app.security import require_api_key

    _, path = create(mysql_client, headers, ROOT + "/activity-versions", activity_payload(policies))
    app.dependency_overrides[require_api_key] = lambda: Principal("dev-author", frozenset({Role.author, Role.instructor}))
    try:
        assert mysql_client.post(path + "/review", json=APPROVAL).status_code == 403
    finally:
        del app.dependency_overrides[require_api_key]
    approved = review(mysql_client, role_headers["instructor"], path)
    assert review(mysql_client, role_headers["instructor"], path) == approved
    for decision in [{**APPROVAL, "note": "Different note"}, {"decision": "rejected", "note": "Different decision"}]:
        assert mysql_client.post(path + "/review", headers=role_headers["instructor"], json=decision).status_code == 409
    assert mysql_client.get(path, headers=headers).json() == approved


def test_review_concurrency_is_single_terminal_decision(mysql_client, headers, role_headers):
    _, path = create(mysql_client, headers, ROOT + "/policy-versions", EXAMPLES["policies"][0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda decision: mysql_client.post(path + "/review", headers=role_headers["instructor"],
                                      json={"decision": decision, "note": decision}), ["approved", "rejected"]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    final = mysql_client.get(path, headers=headers).json()
    assert final == next(response.json() for response in responses if response.status_code == 200)


def test_review_failure_rolls_back_status_and_attribution(mysql_client, mysql_engine, headers, role_headers):
    draft, path = create(mysql_client, headers, ROOT + "/policy-versions", EXAMPLES["policies"][0])
    def fail_review(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE policy_versions"):
            raise OperationalError("private SQL", {}, Exception("private data"))
    event.listen(mysql_engine, "before_cursor_execute", fail_review)
    try:
        response = mysql_client.post(path + "/review", headers=role_headers["instructor"], json=APPROVAL)
        assert response.status_code == 503 and response.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail_review)
    assert mysql_client.get(path, headers=headers).json() == draft
    assert mysql_client.get(ROOT + "/policies/" + draft["id"], headers=headers).status_code == 404


def test_activity_policy_references_and_atomic_mapping_insert(mysql_client, mysql_engine, headers, role_headers, policies):
    payload = activity_payload(policies)
    draft, _ = create(mysql_client, headers, ROOT + "/policy-versions", {**EXAMPLES["policies"][0], "version": 2})
    rejected, rp = create(mysql_client, headers, ROOT + "/policy-versions", {**EXAMPLES["policies"][0], "version": 3})
    review(mysql_client, role_headers["instructor"], rp, {"decision": "rejected", "note": "Needs revision"})
    for policy_id, status in [(str(uuid4()), 404), (draft["id"], 404), (rejected["id"], 404), (policies["safety"]["id"], 422)]:
        assert mysql_client.post(ROOT + "/activity-versions", headers=headers,
                                 json={**payload, "learning_science_policy_id": policy_id}).status_code == status
    assert mysql_client.post(ROOT + "/activity-versions", headers=headers,
                             json={**payload, "safety_policy_id": policies["learning_science"]["id"]}).status_code == 422
    def fail_mapping(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO component_activity_mappings"):
            raise OperationalError("private SQL", {}, Exception("private data"))
    event.listen(mysql_engine, "before_cursor_execute", fail_mapping)
    try:
        response = mysql_client.post(ROOT + "/activity-versions", headers=headers, json=payload)
        assert response.status_code == 503 and response.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(mysql_engine, "before_cursor_execute", fail_mapping)
    with mysql_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ActivityVariant)) == 0
        assert connection.scalar(select(func.count()).select_from(ComponentActivityMapping)) == 0


def test_versions_are_retained_pinned_unique_and_immutable(mysql_client, headers, role_headers, policies):
    payload = activity_payload(policies)
    first, path = create(mysql_client, headers, ROOT + "/activity-versions", payload)
    first = review(mysql_client, role_headers["instructor"], path)
    assert mysql_client.post(ROOT + "/activity-versions", headers=headers, json={**payload, "code": payload["code"].lower()}).status_code == 409
    assert mysql_client.post(ROOT + "/policy-versions", headers=headers, json=EXAMPLES["policies"][0]).status_code == 409
    new_policy, pp = create(mysql_client, headers, ROOT + "/policy-versions", {**EXAMPLES["policies"][0], "version": 2})
    review(mysql_client, role_headers["instructor"], pp)
    second, sp = create(mysql_client, headers, ROOT + "/activity-versions", {**payload, "version": 2, "learning_science_policy_id": new_policy["id"]})
    assert mysql_client.get(ROOT + "/activities", headers=headers).json()["items"] == [first]
    second = review(mysql_client, role_headers["instructor"], sp)
    assert mysql_client.get(ROOT + "/activities", headers=headers).json()["items"] == [first, second]
    assert first["learning_science_policy_id"] == policies["learning_science"]["id"]
    assert mysql_client.get(path, headers=headers).json() == first
    for route in [path, pp, ROOT + "/activities/" + first["id"], ROOT + "/policies/" + new_policy["id"]]:
        for method in ["PATCH", "DELETE"]:
            assert mysql_client.request(method, route, headers=headers, json={"title": "Changed"}).status_code == 405


def test_catalog_filtering_pagination_and_authoring_scope(mysql_client, headers, role_headers, policies):
    approved = []
    for index in range(3):
        _, path = create(mysql_client, headers, ROOT + "/activity-versions", activity_payload(policies, index))
        approved.append(review(mysql_client, role_headers["instructor"], path))
    items = mysql_client.get(ROOT + "/activities", headers=headers).json()["items"]
    assert [item["code"] for item in items] == sorted(item["code"] for item in items)
    assert mysql_client.get(ROOT + "/activities?limit=1&offset=1", headers=headers).json()["items"] == items[1:2]
    assert mysql_client.get(ROOT + "/activities?offset=100", headers=headers).json()["items"] == []
    assert len(mysql_client.get(ROOT + "/activities?component=learning_tasks", headers=headers).json()["items"]) == 2
    assert len(mysql_client.get(ROOT + "/activities?activity_type=worked_example&component=procedural_information", headers=headers).json()["items"]) == 1
    assert mysql_client.get(ROOT + "/activities?activity_type=constructed_response&component=part_task_practice", headers=headers).json()["items"] == []
    assert mysql_client.get(ROOT + "/activity-versions", headers=role_headers["author"]).json()["items"] == []
    assert len(mysql_client.get(ROOT + "/activity-versions?status=approved", headers=role_headers["instructor"]).json()["items"]) == 3
    assert mysql_client.get(ROOT + "/activity-versions?status=draft", headers=headers).json()["items"] == []
    assert len(mysql_client.get(ROOT + "/policies?category=safety", headers=headers).json()["items"]) == 1
    for kind in ["activities", "policies", "activity-versions", "policy-versions"]:
        for query in ["limit=0", "limit=101", "offset=-1"]:
            assert mysql_client.get(ROOT + "/" + kind + "?" + query, headers=headers).status_code == 422
    for query in ["component=quiz", "activity_type=simulation"]:
        assert mysql_client.get(ROOT + "/activities?" + query, headers=headers).status_code == 422


def test_database_catalog_constraints(mysql_client, mysql_engine, headers, role_headers, policies):
    item, path = create(mysql_client, headers, ROOT + "/activity-versions", activity_payload(policies))
    invalid_updates = [
        update(ActivityVariant).values(version=0), update(ActivityVariant).values(estimated_minutes=0),
        update(ActivityVariant).values(activity_type="simulation"), update(ActivityVariant).values(evidence_tier="established"),
        update(ActivityVariant).values(review_scope="university"), update(ActivityVariant).values(safety_policy_id=str(uuid4())),
        update(ActivityVariant).values(review_status="approved"),
        update(PolicyVersion).values(category="mastery"), update(PolicyVersion).values(reviewed_by="dev-author"),
        insert(ComponentActivityMapping).values(activity_variant_id=item["id"], component="quiz", rationale="Invalid"),
        insert(ComponentActivityMapping).values(activity_variant_id=item["id"], component="learning_tasks", rationale="Duplicate"),
    ]
    for statement in invalid_updates:
        with pytest.raises((IntegrityError, OperationalError)) as error:
            with mysql_engine.begin() as connection:
                connection.execute(statement)
        assert error.value.orig.args[0] in {1062, 1452, 3819}
