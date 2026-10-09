import pytest

from app.attempt_schemas import AttemptReview, SelectedAnswer, WrittenAnswer
from app.generator import build_sequence
from app.planner import build_plan
from app.planner_fixtures import synthetic_input
from app.scoring import ScoringError, request_hash, reviewed_points, selected_points, validate_answer


def steps():
    snapshot = synthetic_input("beginner")
    return build_sequence(snapshot, build_plan(snapshot)).steps


def test_selected_correct_and_incorrect_use_private_key():
    step = steps()[1]
    for choice in step.content.choices:
        answer = SelectedAnswer(activity_type="selected_response", choice_id=choice.id)
        assert selected_points(step, answer) == {"FOCUS": int(choice.id == step.content.correct_choice_id)}
    with pytest.raises(ScoringError):
        selected_points(step, SelectedAnswer(activity_type="selected_response", choice_id="missing"))


def test_text_is_data_and_format_must_match():
    answer = WrittenAnswer(activity_type="constructed_response", text="__import__('os').system('false')")
    validate_answer(steps()[-1], answer)
    with pytest.raises(ScoringError):
        validate_answer(steps()[1], answer)
    with pytest.raises(ScoringError):
        validate_answer(steps()[0], answer)
    with pytest.raises(ScoringError):
        selected_points(steps()[-1], answer)


@pytest.mark.parametrize("criteria", [[{"code": "TARGET", "points": 2}],
    [{"code": "TARGET", "points": 3}, {"code": "FOCUS", "points": 1}],
    [{"code": "TARGET", "points": 2}, {"code": "FOCUS", "points": 2}],
    [{"code": "OTHER", "points": 1}, {"code": "FOCUS", "points": 1}],
    [{"code": "TARGET", "points": 1}, {"code": "TARGET", "points": 1}]] )
def test_review_requires_exact_criteria_and_rubric_bounds(criteria):
    with pytest.raises(ScoringError):
        reviewed_points(steps()[-1], AttemptReview(criteria=criteria, note="Synthetic"))


def test_review_partial_credit_and_canonical_request_hash():
    step = steps()[-1]
    review = AttemptReview(criteria=[{"code": "FOCUS", "points": 0}, {"code": "TARGET", "points": 1}], note="Synthetic")
    assert reviewed_points(step, review) == {"FOCUS": 0, "TARGET": 1}
    with pytest.raises(ScoringError):
        reviewed_points(steps()[1], review)
    answer = WrittenAnswer(activity_type="constructed_response", text="Repair and trace")
    assert request_hash("a", answer) == request_hash("a", answer)
    assert request_hash("a", answer) != request_hash("b", answer)
    assert request_hash("a", answer) != request_hash("a", answer.model_copy(update={"text": "Changed"}))
