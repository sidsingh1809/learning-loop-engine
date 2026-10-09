"""Pure provisional scoring. Learner text is data and is never executed."""
import hashlib
import json

from app.attempt_schemas import AttemptReview

SELECTED_SCORER = "selected-response-v1"
INSTRUCTOR_SCORER = "instructor-rubric-v1"


class ScoringError(ValueError):
    pass


def request_hash(activity_id, answer):
    value = {"activity_id": str(activity_id), "response": answer.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_answer(step, answer):
    if step.content.activity_type == "worked_example":
        raise ScoringError("Worked examples do not accept scored attempts")
    if answer.activity_type != step.content.activity_type:
        raise ScoringError("Response format must match the activity")
    if answer.activity_type == "selected_response" and answer.choice_id not in {c.id for c in step.content.choices}:
        raise ScoringError("Choice is not part of this activity")


def selected_points(step, answer):
    validate_answer(step, answer)
    if step.rubric.scoring_method != "selected_response":
        raise ScoringError("This activity requires instructor scoring")
    correct = answer.choice_id == step.content.correct_choice_id
    return {c.code: c.max_points if correct else 0 for c in step.rubric.criteria}


def reviewed_points(step, review: AttemptReview):
    if step.rubric.scoring_method != "instructor_review":
        raise ScoringError("Only constructed responses accept instructor scoring")
    points = {c.code: c.points for c in review.criteria}
    if len(points) != len(review.criteria) or set(points) != {c.code for c in step.rubric.criteria}:
        raise ScoringError("Score every rubric criterion exactly once")
    if any(points[c.code] > c.max_points for c in step.rubric.criteria):
        raise ScoringError("Criterion points exceed the saved rubric maximum")
    return points
