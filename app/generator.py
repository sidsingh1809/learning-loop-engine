"""Pure, bounded programming-pilot templates and a validation boundary for Track B."""
import hashlib
import json

from pydantic import ValidationError

from app.generation_schemas import GeneratedSequence
from app.planner import PlanningError, build_plan
from app.planner_schemas import DecisionRead, PlannerInput

GENERATOR_VERSION = "track-b-template-v1"
TEMPLATE_VERSION = "positive-sales-v1"
CODE = "sales = [4, -2, 3]\ntotal = 0\nfor sale in sales:\n    if sale > 0:\n        total = sale\nprint(total)"
SCENARIO = "A synthetic shop needs the sum of positive sales [4, -2, 3]. The expected total is 7, but this program prints 3."
FOCUS = {
    "VARIABLES": ("Trace total before and after each assignment.", "The assignment replaces total: 0 becomes 4, then 3. Use total += sale to retain the running sum."),
    "EXPRESSIONS": ("Compare total = sale with total = total + sale.", "Replacement gives 3; accumulation evaluates 4 + 3 to produce 7."),
    "CONDITIONALS": ("Identify which sales satisfy sale > 0 and which updates are skipped.", "4 and 3 enter the branch; -2 is skipped. Only positive sales should update the sum."),
    "LOOPS": ("Trace each loop iteration, including the skipped negative sale.", "Three iterations visit 4, -2 and 3; accumulation leaves totals 4, 4 and 7."),
    "DEBUGGING": ("Compare expected and observed behavior, locate the faulty update and justify a repair.", "total = sale overwrites the accumulated value. Replace it with total += sale and check that [4, -2, 3] produces 7."),
}


class GenerationError(ValueError):
    pass


def validate_plan(snapshot: PlannerInput, decision: DecisionRead):
    try:
        replay = build_plan(snapshot)
    except PlanningError as exc:
        raise GenerationError("Saved plan cannot be replayed") from exc
    if replay != decision:
        raise GenerationError("Saved plan or step order differs from its pinned input")
    skills = {s.id: s for s in snapshot.skills}
    target, focus = skills[str(decision.target_skill_id)], skills[str(decision.focus_skill_id)]
    if target.code != "DEBUGGING" or target.skill_kind != "non_routine" or focus.code not in FOCUS:
        raise GenerationError("Template v1 supports only the synthetic DEBUGGING target and its programming prerequisites")
    if focus.code != "DEBUGGING" and focus.skill_kind != "routine":
        raise GenerationError("Programming prerequisite templates require routine focus skills")
    return focus


def validate_output(raw, snapshot: PlannerInput, decision: DecisionRead) -> GeneratedSequence:
    """Reject structurally valid content that changes the saved instructional sequence."""
    validate_plan(snapshot, decision)
    try:
        result = GeneratedSequence.model_validate(raw.model_dump(mode="json") if isinstance(raw, GeneratedSequence) else raw)
    except ValidationError as exc:
        raise GenerationError("Generated content or rubric is invalid") from exc
    if (result.plan_fingerprint != decision.input_fingerprint
            or result.learning_science_policy_id != snapshot.learning_science_policy.id
            or result.safety_policy_id != snapshot.safety_policy.id
            or result.estimated_minutes != decision.estimated_minutes
            or len(result.steps) != len(decision.steps)):
        raise GenerationError("Generated sequence changes plan provenance or duration")
    catalog = {str(a.id): a for a in snapshot.activities}
    for output, planned in zip(result.steps, decision.steps):
        for name in ["position", "role", "skill_id", "activity_variant_id", "components", "support_level", "estimated_minutes"]:
            if getattr(output, name) != getattr(planned, name):
                raise GenerationError("Generated step changes saved ordering, alignment or support")
        if (output.target_skill_id != decision.target_skill_id or output.focus_skill_id != decision.focus_skill_id
                or output.context_key != decision.context_key
                or output.content.activity_type != catalog[str(planned.activity_variant_id)].activity_type):
            raise GenerationError("Generated step changes the whole-task context or catalog format")
        if len(output.components) != len(set(output.components)):
            raise GenerationError("Generated components must be unique")
        if output.content.activity_type == "worked_example":
            for component in ["supportive_information", "procedural_information"]:
                if (getattr(output.content, component) is not None) != (component in output.components):
                    raise GenerationError("Worked example information must match planned components")
        if output.content.activity_type == "selected_response":
            if (output.role != "focus_practice" or output.components != ["part_task_practice"]
                    or len(output.rubric.criteria) != 1 or output.rubric.criteria[0].skill_id != decision.focus_skill_id):
                raise GenerationError("Selected-response evidence must concern the planned routine focus only")
        if output.content.activity_type == "constructed_response":
            if {c.skill_id for c in output.rubric.criteria} != {decision.target_skill_id, decision.focus_skill_id}:
                raise GenerationError("Whole-task rubric must cover target and prerequisite focus")
    if sum(s.estimated_minutes for s in result.steps) != result.estimated_minutes:
        raise GenerationError("Generated durations do not sum to the plan total")
    return result


def build_sequence(snapshot: PlannerInput, decision: DecisionRead) -> GeneratedSequence:
    focus = validate_plan(snapshot, decision)
    instruction, expected = FOCUS[focus.code]
    catalog = {str(a.id): a for a in snapshot.activities}
    steps = []
    for planned in decision.steps:
        kind = catalog[str(planned.activity_variant_id)].activity_type
        rubric = {"version": "synthetic-rubric-v1", "scoring_method": "none", "criteria": [],
                  "max_points": 0, "formal_certification": False}
        if kind == "worked_example":
            content = {"activity_type": kind, "prompt": SCENARIO + " " + instruction, "code": CODE,
                       "explanation": expected + " Repair the update with total += sale; the full positive-sales task then produces 7.",
                       "supportive_information": "Compare expected and observed behavior. Trace a small case to locate the defect; verify the repair against the whole requirement." if "supportive_information" in planned.components else None,
                       "procedural_information": instruction + " Start with total = 0, visit each sale and record the updated value." if "procedural_information" in planned.components else None}
        elif kind == "selected_response":
            # Planner permits this only for developing routine automaticity skills.
            expression = focus.code == "EXPRESSIONS"
            content = {"activity_type": kind,
                       "prompt": "In the same sales task, total is 4 and sale is 3. " + ("What does total + sale evaluate to?" if expression else "After total = sale, what value is stored in total?"),
                       "choices": [{"id": "a", "text": "3"}, {"id": "b", "text": "7"}, {"id": "c", "text": "4"}],
                       "correct_choice_id": "b" if expression else "a",
                       "explanation": "4 + 3 evaluates to 7." if expression else "Assignment replaces the previous value with 3; it does not accumulate."}
            if focus.code not in {"VARIABLES", "EXPRESSIONS"}:
                raise GenerationError("No automaticity template exists for this focus")
            rubric.update(scoring_method="selected_response", max_points=1,
                          criteria=[{"code": "FOCUS", "skill_id": decision.focus_skill_id, "description": instruction,
                                     "max_points": 1, "expected_response": content["correct_choice_id"]}])
        else:
            content = {"activity_type": kind, "prompt": SCENARIO + " Repair the program and explain why the repair meets the positive-sales requirement.",
                       "code": CODE, "response_instructions": "Submit a corrected update, a trace, and a justification. " + instruction + " Code is read as text; it is not executed."}
            criteria = [{"code": "TARGET", "skill_id": decision.target_skill_id,
                         "description": "Locate the defect, justify the repair and verify the whole-task requirement.",
                         "max_points": 2, "expected_response": "Replace total = sale with total += sale. The trace is 4, 4, 7. Explain replacement versus accumulation and check zero/negative-only inputs."}]
            if decision.focus_skill_id != decision.target_skill_id:
                criteria.append({"code": "FOCUS", "skill_id": decision.focus_skill_id, "description": instruction,
                                 "max_points": 1, "expected_response": expected})
            rubric.update(scoring_method="instructor_review", criteria=criteria, max_points=sum(c["max_points"] for c in criteria))
        steps.append({**planned.model_dump(mode="json", exclude={"rationale"}),
                      "target_skill_id": decision.target_skill_id, "focus_skill_id": decision.focus_skill_id,
                      "context_key": decision.context_key, "scenario_id": TEMPLATE_VERSION, "content": content, "rubric": rubric})
    return validate_output({"generator_version": GENERATOR_VERSION, "template_version": TEMPLATE_VERSION,
                            "plan_fingerprint": decision.input_fingerprint,
                            "learning_science_policy_id": snapshot.learning_science_policy.id,
                            "safety_policy_id": snapshot.safety_policy.id,
                            "estimated_minutes": decision.estimated_minutes, "review_scope": "synthetic_only", "steps": steps}, snapshot, decision)


def content_hash(sequence: GeneratedSequence):
    return hashlib.sha256(json.dumps(sequence.model_dump(mode="json"), sort_keys=True,
                                     separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def learner_step(step):
    """Deliver task instructions and criteria while keeping future scoring keys private."""
    values = step.model_dump(mode="json")
    if step.content.activity_type == "selected_response":
        values["content"].pop("correct_choice_id")
        values["content"].pop("explanation")
    for criterion in values["rubric"]["criteria"]:
        criterion.pop("expected_response")
    return values
