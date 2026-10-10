"""Pure deterministic next-action decisions; no database, clock or generation calls."""
import hashlib
import json

from app.domain_graph import topological_order
from app.planner_schemas import DecisionRead, PlannerInput

PLANNER_VERSION = "track-a-v1"


class PlanningError(ValueError):
    pass


def canonical_snapshot(snapshot: PlannerInput):
    values = snapshot.model_dump(mode="json")
    # Preserve fingerprints of immutable Day 7-9 snapshots predating this field.
    for state in values["states"]:
        if state["policy_version"] is None:
            del state["policy_version"]
    for name, key in [("skills", lambda x: (x["code"], x["id"])),
                      ("states", lambda x: x["skill_id"]),
                      ("activities", lambda x: x["id"])]:
        values[name] = sorted(values[name], key=key)
    values["edges"] = sorted(values["edges"])
    for item in values["activities"]:
        item["mappings"] = sorted(item["mappings"], key=lambda x: x["component"])
    return values


def build_plan(snapshot: PlannerInput) -> DecisionRead:
    values = canonical_snapshot(snapshot)
    fingerprint = hashlib.sha256(json.dumps(
        {"planner_version": PLANNER_VERSION, "input": values}, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    skills = {item.id: item for item in snapshot.skills}
    states = {item.skill_id: item for item in snapshot.states}
    order = topological_order(snapshot.skills, snapshot.edges)
    if (not order or len(skills) != len(snapshot.skills) or len(states) != len(snapshot.states)
            or set(states) != set(skills) or snapshot.target_skill_id not in skills):
        raise PlanningError("Planning requires a valid graph and exactly one state per skill")
    if any(s.skill_kind == "non_routine" and s.requires_automaticity for s in snapshot.skills):
        raise PlanningError("Only routine skills can require automaticity")
    policies = [snapshot.learning_science_policy, snapshot.safety_policy]
    if any(p.review_status != "approved" for p in policies) or [p.category for p in policies] != ["learning_science", "safety"]:
        raise PlanningError("Planning requires approved policies of the correct categories")
    prerequisites = {sid: set() for sid in skills}
    for sid, required in snapshot.edges:
        prerequisites[sid].add(required)
    relevant, pending = set(), list(prerequisites[snapshot.target_skill_id])
    while pending:
        sid = pending.pop()
        if sid not in relevant:
            relevant.add(sid)
            pending.extend(prerequisites[sid])
    focus_id = next((sid for sid in order if sid in relevant and states[sid].band != "secure"), snapshot.target_skill_id)
    focus, target, state = skills[focus_id], skills[snapshot.target_skill_id], states[focus_id]
    support = "minimal" if state.band == "secure" else "high"
    action = {"unknown": "diagnostic_or_guided", "developing": "guided_practice", "secure": "independent_task"}[state.band]
    rationale = ["Prerequisites are considered before the target; ties follow skill code then ID."]
    rationale.append("Focus {} {}.".format(focus.code, "is a prerequisite of " + target.code if focus_id != target.id else "is the requested target"))
    rationale.append({"unknown": "No evidence is available for the focus: offer diagnosis or guided work; unknown does not mean low proficiency.",
                      "developing": "Observed developing performance: retain support and practice the focus.",
                      "secure": "Observed secure performance: fade support and attempt a standard whole task; no certification is inferred."}[state.band])
    eligible = sorted((a for a in snapshot.activities if a.review_status == "approved"
                       and str(a.learning_science_policy_id) == str(policies[0].id)
                       and str(a.safety_policy_id) == str(policies[1].id)),
                      key=lambda a: (a.estimated_minutes, a.code, a.version, str(a.id)))

    def choose(kind, components, required=True):
        item = next((a for a in eligible if a.activity_type == kind
                     and set(components) <= {m.component for m in a.mappings}), None)
        if item is None and required:
            raise PlanningError("No approved {} activity maps the required components under the pinned policies".format(kind))
        return item

    steps = []

    def step(activity, role, sid, components, reason):
        steps.append({"position": len(steps) + 1, "role": role, "skill_id": sid,
                      "activity_variant_id": activity.id, "components": components,
                      "support_level": support, "estimated_minutes": activity.estimated_minutes, "rationale": reason})

    final = choose("constructed_response", ["learning_tasks"])
    if support == "high":
        components = ["learning_tasks"]
        if target.skill_kind == "non_routine" or focus.skill_kind == "non_routine":
            components.append("supportive_information")
        if focus.skill_kind == "routine":
            components.append("procedural_information")
        context = choose("worked_example", components)
        minimum = context.estimated_minutes + final.estimated_minutes
        if minimum > snapshot.time_budget_minutes:
            raise PlanningError("Time budget is too short; the connected supported sequence requires at least {} minutes".format(minimum))
        step(context, "whole_task_context", target.id, components,
             "Introduce the whole target task, with reasoning support for non-routine aspects and just-in-time procedures for routine focus aspects.")
        if focus.skill_kind == "routine" and focus.requires_automaticity and state.band == "developing":
            practice = choose("selected_response", ["part_task_practice"], required=False)
            if practice and minimum + practice.estimated_minutes <= snapshot.time_budget_minutes:
                step(practice, "focus_practice", focus_id, ["part_task_practice"],
                     "Observed developing performance on a routine automaticity skill warrants practice, followed by return to the whole task.")
            else:
                rationale.append("Optional automaticity practice is omitted because no eligible format fits the remaining budget.")
        step(final, "whole_task_return", target.id, ["learning_tasks"],
             "Return to the same whole-task context and elicit focus-skill reasoning; constructed responses require instructor review.")
    else:
        if final.estimated_minutes > snapshot.time_budget_minutes:
            raise PlanningError("Time budget is too short; the whole task requires at least {} minutes".format(final.estimated_minutes))
        step(final, "whole_task", target.id, ["learning_tasks"],
             "Attempt the whole target task with faded support and instructor-reviewed reasoning.")
    total = sum(s["estimated_minutes"] for s in steps)
    rationale.append("Activity ties follow full estimated duration, code, version, then ID; durations are never shortened to fit.")
    return DecisionRead(planner_version=PLANNER_VERSION, input_fingerprint=fingerprint,
                        target_skill_id=target.id, focus_skill_id=focus_id,
                        context_key="domain:{}:target:{}".format(snapshot.domain_version_id, target.id), action=action,
                        support_level=support, complexity="standard" if support == "minimal" else "introductory",
                        rationale=rationale, time_budget_minutes=snapshot.time_budget_minutes,
                        estimated_minutes=total, unused_minutes=snapshot.time_budget_minutes - total,
                        completion_conditions=["Complete the connected whole task and capture evidence for the focus skill.",
                                               "Hold constructed responses for authorized instructor review before updating learner state.",
                                               "Part-task success alone cannot certify competency; this plan does not update state."],
                        formal_certification=False, review_scope="synthetic_only", steps=steps)
