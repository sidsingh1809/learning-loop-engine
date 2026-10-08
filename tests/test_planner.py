from copy import deepcopy
from random import Random
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.planner import PlanningError, build_plan
from app.planner_fixtures import synthetic_input
from app.planner_schemas import PlannerInput


def test_repeatable_beginner_and_experienced_decisions():
    beginner, experienced = synthetic_input("beginner"), synthetic_input("experienced")
    a, b = build_plan(beginner), build_plan(experienced)
    assert a == build_plan(beginner)
    assert str(a.focus_skill_id) == beginner.skills[0].id
    assert a.action == "guided_practice" and a.support_level == "high" and a.complexity == "introductory"
    assert [s.role for s in a.steps] == ["whole_task_context", "focus_practice", "whole_task_return"]
    assert a.estimated_minutes == 19
    assert str(b.focus_skill_id) == experienced.target_skill_id
    assert b.action == "independent_task" and b.support_level == "minimal" and b.complexity == "standard"
    assert [s.role for s in b.steps] == ["whole_task"] and b.estimated_minutes == 10
    assert not a.formal_certification and not b.formal_certification
    assert a.rationale and b.rationale and a.input_fingerprint != b.input_fingerprint


def test_unknown_is_not_low_and_never_certifies_or_changes_input():
    snapshot = synthetic_input()
    before = deepcopy(snapshot)
    plan = build_plan(snapshot)
    assert snapshot == before
    assert plan.action == "diagnostic_or_guided" and "unknown does not mean low" in " ".join(plan.rationale)
    assert [s.role for s in plan.steps] == ["whole_task_context", "whole_task_return"]
    assert "procedural_information" in plan.steps[0].components
    assert "supportive_information" in plan.steps[0].components
    assert plan.steps[0].skill_id == plan.steps[-1].skill_id == plan.target_skill_id


def test_order_independence_including_catalog_mappings():
    snapshot = synthetic_input("beginner")
    expected = build_plan(snapshot)
    for seed in range(8):
        value = deepcopy(snapshot)
        rng = Random(seed)
        for items in [value.skills, value.states, value.edges, value.activities]:
            rng.shuffle(items)
        for activity in value.activities:
            rng.shuffle(activity.mappings)
        assert build_plan(value) == expected


@pytest.mark.parametrize("profile,minutes,total", [("unknown", 16, 16), ("beginner", 16, 16), ("beginner", 19, 19), ("experienced", 10, 10)])
def test_complete_activity_durations_and_optional_practice(profile, minutes, total):
    plan = build_plan(synthetic_input(profile, minutes))
    assert plan.estimated_minutes == total == sum(s.estimated_minutes for s in plan.steps)
    assert plan.unused_minutes == minutes - total
    if profile == "beginner" and minutes == 16:
        assert "omitted" in " ".join(plan.rationale)


@pytest.mark.parametrize("profile,budget", [("unknown", 15), ("beginner", 18 - 3), ("experienced", 9)])
def test_cannot_fit_returns_actionable_failure(profile, budget):
    with pytest.raises(PlanningError, match="requires at least"):
        build_plan(synthetic_input(profile, budget))


@pytest.mark.parametrize("kind,automaticity", [("routine", False), ("non_routine", False)])
def test_part_task_only_for_observed_routine_automaticity(kind, automaticity):
    snapshot = synthetic_input("beginner")
    snapshot.skills[0].skill_kind, snapshot.skills[0].requires_automaticity = kind, automaticity
    plan = build_plan(snapshot)
    assert all("part_task_practice" not in s.components for s in plan.steps)
    if kind == "non_routine":
        assert "procedural_information" not in plan.steps[0].components


def test_transitive_prerequisite_and_unrelated_gap():
    snapshot = synthetic_input("experienced")
    snapshot.states[1].band = "developing"
    snapshot.states[0].band = "developing"
    # An unrelated root with an earlier code must not become the focus.
    extra = snapshot.skills[0].model_copy(update={"id": str(uuid4()), "code": "AAA"})
    snapshot.skills.append(extra)
    snapshot.states.append(snapshot.states[0].model_copy(update={"skill_id": extra.id}))
    assert str(build_plan(snapshot).focus_skill_id) == snapshot.skills[0].id
    snapshot.states[0].band = "secure"
    assert str(build_plan(snapshot).focus_skill_id) == snapshot.skills[1].id


@pytest.mark.parametrize("change", ["cycle", "foreign_edge", "missing_state", "duplicate_state", "target", "classification"])
def test_invalid_snapshot_fails_closed(change):
    snapshot = synthetic_input()
    if change == "cycle": snapshot.edges.append((snapshot.skills[0].id, snapshot.target_skill_id))
    if change == "foreign_edge": snapshot.edges.append((snapshot.target_skill_id, str(uuid4())))
    if change == "missing_state": snapshot.states.pop()
    if change == "duplicate_state": snapshot.states.append(snapshot.states[0])
    if change == "target": snapshot.target_skill_id = str(uuid4())
    if change == "classification": snapshot.skills[-1].requires_automaticity = True
    with pytest.raises(PlanningError): build_plan(snapshot)


@pytest.mark.parametrize("change", ["draft", "rejected", "wrong_policy", "missing_mapping", "missing_activity"])
def test_only_approved_compatible_catalog_candidates(change):
    snapshot = synthetic_input()
    worked = snapshot.activities[0]
    if change in ("draft", "rejected"): worked.review_status = change
    if change == "wrong_policy": worked.safety_policy_id = uuid4()
    if change == "missing_mapping": worked.mappings = [m for m in worked.mappings if m.component != "procedural_information"]
    if change == "missing_activity": snapshot.activities.pop(0)
    with pytest.raises(PlanningError, match="No approved worked_example"):
        build_plan(snapshot)


def test_policy_approval_and_evidence_provenance_required():
    snapshot = synthetic_input()
    snapshot.learning_science_policy.review_status = "draft"
    with pytest.raises(PlanningError, match="approved policies"):
        build_plan(snapshot)
    values = synthetic_input().model_dump(mode="json")
    values["states"][0]["band"] = "secure"
    with pytest.raises(ValidationError): PlannerInput(**values)


def test_catalog_ties_choose_duration_then_code_then_version():
    snapshot = synthetic_input()
    variant = deepcopy(snapshot.activities[-1])
    variant.id, variant.code = uuid4(), "AAA"
    snapshot.activities.append(variant)
    assert build_plan(snapshot).steps[-1].activity_variant_id == variant.id
    variant.estimated_minutes = 11
    assert build_plan(snapshot).steps[-1].activity_variant_id == snapshot.activities[-2].id
