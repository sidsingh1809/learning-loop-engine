"""Engineering-only mastery policy; thresholds are provisional, not calibrated."""

STATE_POLICY_VERSION = "provisional-mastery-v1"
STATE_FIELDS = ("band", "evidence_count", "revision", "whole_task_evidence_count", "part_task_evidence_count",
                "whole_task_attempt_count", "whole_task_points", "whole_task_max_points", "policy_version")


def advance_state(before, evidence):
    """One revision per scored attempt/skill, one evidence count per criterion.

    Secure requires two whole-task attempts and >=80% of cumulative whole-task
    rubric points for this skill. Part-task points never enter this ratio.
    New poor whole-task evidence can lower the band; there is no time decay.
    """
    if not evidence:
        raise ValueError("State application requires evidence")
    after = dict(before)
    whole = [e for e in evidence if e.evidence_kind == "whole_task"]
    after["evidence_count"] += len(evidence)
    after["revision"] += 1
    after["whole_task_evidence_count"] += len(whole)
    after["part_task_evidence_count"] += len(evidence) - len(whole)
    after["whole_task_attempt_count"] += bool(whole)
    after["whole_task_points"] += sum(e.points for e in whole)
    after["whole_task_max_points"] += sum(e.max_points for e in whole)
    after["band"] = "secure" if (after["whole_task_attempt_count"] >= 2 and
        after["whole_task_points"] * 5 >= after["whole_task_max_points"] * 4) else "developing"
    after["policy_version"] = STATE_POLICY_VERSION
    return after
