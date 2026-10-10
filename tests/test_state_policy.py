from types import SimpleNamespace

import pytest

from app.state_policy import STATE_POLICY_VERSION, advance_state


def initial():
    return dict(band="unknown", evidence_count=0, revision=0, whole_task_evidence_count=0,
                part_task_evidence_count=0, whole_task_attempt_count=0, whole_task_points=0,
                whole_task_max_points=0, policy_version=None)


def evidence(points, maximum=10, kind="whole_task"):
    return SimpleNamespace(points=points, max_points=maximum, evidence_kind=kind)


def test_unknown_and_failed_observation_are_distinct():
    before = initial()
    after = advance_state(before, [evidence(0)])
    assert before == initial()
    assert after["band"] == "developing" and after["evidence_count"] == after["revision"] == 1
    assert after["policy_version"] == STATE_POLICY_VERSION
    with pytest.raises(ValueError):
        advance_state(before, [])


@pytest.mark.parametrize("first,second,band", [(10, 10, "secure"), (8, 8, "secure"),
                                               (7, 8, "developing"), (10, 5, "developing")])
def test_whole_task_threshold_and_minimum_attempts(first, second, band):
    state = advance_state(initial(), [evidence(first)])
    assert state["band"] == "developing"
    assert advance_state(state, [evidence(second)])["band"] == band


def test_part_task_never_supplies_secure_points_or_whole_task_attempts():
    state = initial()
    for _ in range(20):
        state = advance_state(state, [evidence(10, kind="part_task")])
    assert state["band"] == "developing" and state["part_task_evidence_count"] == 20
    assert state["whole_task_attempt_count"] == state["whole_task_max_points"] == 0
    state = advance_state(state, [evidence(0)])
    state = advance_state(state, [evidence(0)])
    assert state["band"] == "developing"


def test_multiple_criteria_count_once_as_whole_task_attempt_and_revision():
    state = advance_state(initial(), [evidence(1, 1), evidence(2, 2)])
    assert state["evidence_count"] == 2
    assert state["whole_task_attempt_count"] == state["revision"] == 1
    assert state["whole_task_points"] == state["whole_task_max_points"] == 3


def test_poor_whole_task_can_lower_band_without_erasing_history():
    state = advance_state(advance_state(initial(), [evidence(10)]), [evidence(10)])
    assert state["band"] == "secure"
    state = advance_state(state, [evidence(0)])
    assert state["band"] == "developing" and state["revision"] == 3


def test_old_snapshot_fingerprint_survives_optional_policy_field():
    from app.planner import build_plan, canonical_snapshot
    from app.planner_fixtures import synthetic_input
    from app.planner_schemas import PlannerInput
    original = synthetic_input()
    old = canonical_snapshot(original)
    assert all("policy_version" not in s for s in old["states"])
    assert build_plan(PlannerInput(**old)) == build_plan(original)
