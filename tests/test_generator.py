from copy import deepcopy

import pytest

from app.generator import GenerationError, build_sequence, content_hash, learner_step, validate_output
from app.planner import build_plan
from app.planner_fixtures import synthetic_input
from app.planner_schemas import DecisionRead, PlannerInput


@pytest.mark.parametrize("profile,count", [("unknown", 2), ("beginner", 3), ("experienced", 1)])
def test_connected_templates_are_repeatable_and_aligned(profile, count):
    snapshot = synthetic_input(profile)
    plan = build_plan(snapshot)
    seq = build_sequence(snapshot, plan)
    assert seq == build_sequence(snapshot, plan)
    assert content_hash(seq) == content_hash(build_sequence(snapshot, plan))
    assert len(seq.steps) == count
    assert seq.estimated_minutes == plan.estimated_minutes
    assert [s.position for s in seq.steps] == list(range(1, count + 1))
    assert {s.context_key for s in seq.steps} == {plan.context_key}
    assert {s.scenario_id for s in seq.steps} == {"positive-sales-v1"}
    assert all(s.target_skill_id == plan.target_skill_id and s.focus_skill_id == plan.focus_skill_id for s in seq.steps)
    assert seq.steps[-1].content.activity_type == "constructed_response"
    assert seq.steps[-1].rubric.scoring_method == "instructor_review"
    assert seq.steps[-1].role == ("whole_task" if profile == "experienced" else "whole_task_return")
    assert {c.skill_id for c in seq.steps[-1].rubric.criteria} == {plan.target_skill_id, plan.focus_skill_id}
    if profile == "beginner":
        assert seq.steps[1].content.correct_choice_id == "a"
        assert seq.steps[1].components == ["part_task_practice"]


@pytest.mark.parametrize("focus_code", ["VARIABLES", "EXPRESSIONS", "CONDITIONALS", "LOOPS", "DEBUGGING"])
def test_each_pilot_focus_has_aligned_support(focus_code):
    snapshot = synthetic_input()
    values = snapshot.model_dump(mode="json")
    focus = next(s for s in snapshot.skills if s.code == focus_code)
    reached = False
    for skill in snapshot.skills:
        if skill.id == focus.id:
            reached = True
        if not reached:
            state = next(s for s in values["states"] if s["skill_id"] == skill.id)
            state.update(band="secure", evidence_count=2, revision=1)
    snapshot = PlannerInput(**values)
    plan = build_plan(snapshot)
    seq = build_sequence(snapshot, plan)
    assert str(plan.focus_skill_id) == focus.id
    assert focus.id in {str(c.skill_id) for c in seq.steps[-1].rubric.criteria}
    assert (seq.steps[0].content.procedural_information is not None) == (focus.skill_kind == "routine")


def test_expressions_automaticity_uses_correct_expression_answer():
    values = synthetic_input("beginner").model_dump(mode="json")
    by_id = {s["id"]: s["code"] for s in values["skills"]}
    for state in values["states"]:
        if by_id[state["skill_id"]] == "VARIABLES": state.update(band="secure", evidence_count=2, revision=1)
        if by_id[state["skill_id"]] == "EXPRESSIONS": state.update(band="developing", evidence_count=2, revision=1)
    snapshot = PlannerInput(**values)
    seq = build_sequence(snapshot, build_plan(snapshot))
    assert seq.steps[1].content.correct_choice_id == "b"


def test_learner_projection_hides_answer_keys_and_expected_responses():
    snapshot = synthetic_input("beginner")
    seq = build_sequence(snapshot, build_plan(snapshot))
    selected = learner_step(seq.steps[1])
    assert "correct_choice_id" not in selected["content"] and "explanation" not in selected["content"]
    assert selected["content"]["choices"]
    for step in seq.steps:
        assert all("expected_response" not in c for c in learner_step(step)["rubric"]["criteria"])
    assert seq.steps[1].content.correct_choice_id == "a"


def mutations(raw):
    results = []
    def change(callback):
        value = deepcopy(raw); callback(value); results.append(value)
    change(lambda x: x["steps"].reverse())
    change(lambda x: x["steps"].pop())
    change(lambda x: x.update(estimated_minutes=1))
    change(lambda x: x.update(plan_fingerprint="0" * 64))
    change(lambda x: x.update(safety_policy_id=x["learning_science_policy_id"]))
    for name, value in [("position", True), ("role", "whole_task"), ("context_key", "disconnected"),
                        ("focus_skill_id", raw["steps"][0]["target_skill_id"]), ("estimated_minutes", 1),
                        ("components", ["part_task_practice"]), ("support_level", "minimal"),
                        ("activity_variant_id", raw["steps"][-1]["activity_variant_id"]), ("scenario_id", "other")]:
        change(lambda x, n=name, v=value: x["steps"][0].update({n: v}))
    change(lambda x: x["steps"][1]["content"].update(correct_choice_id="missing"))
    change(lambda x: x["steps"][1]["content"]["choices"][1].update(id="a"))
    change(lambda x: x["steps"][-1]["rubric"].update(max_points=99))
    change(lambda x: x["steps"][-1]["rubric"].update(scoring_method="selected_response"))
    change(lambda x: x["steps"][-1]["rubric"]["criteria"].pop())
    change(lambda x: x["steps"][0]["content"].update(prompt="   "))
    change(lambda x: x["steps"][0]["content"].update(procedural_information=None))
    change(lambda x: x.update(formal_certification=True))
    return results


@pytest.mark.parametrize("index", range(24))
def test_invalid_output_is_rejected(index):
    snapshot = synthetic_input("beginner"); plan = build_plan(snapshot)
    raw = build_sequence(snapshot, plan).model_dump(mode="json")
    variants = mutations(raw)
    if index >= len(variants):
        # Test forbidden rubric certification and duplicate criterion codes too.
        if index == len(variants): raw["steps"][-1]["rubric"]["formal_certification"] = True
        else: raw["steps"][-1]["rubric"]["criteria"][1]["code"] = "TARGET"
    else: raw = variants[index]
    with pytest.raises(GenerationError): validate_output(raw, snapshot, plan)


def test_saved_plan_cannot_be_overridden_and_unsupported_target_is_explicit():
    snapshot = synthetic_input(); plan = build_plan(snapshot)
    altered = plan.model_dump(mode="json"); altered["steps"].reverse()
    with pytest.raises(GenerationError, match="Saved plan"):
        build_sequence(snapshot, DecisionRead(**altered))
    values = snapshot.model_dump(mode="json")
    values["target_skill_id"] = values["skills"][0]["id"]
    snapshot = PlannerInput(**values)
    with pytest.raises(GenerationError, match="DEBUGGING"):
        build_sequence(snapshot, build_plan(snapshot))
