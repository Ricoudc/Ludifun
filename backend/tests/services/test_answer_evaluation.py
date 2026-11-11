import pytest

from app.ai.schemas import EvaluationOutput
from app.services.answer_evaluation import to_evaluation


@pytest.mark.parametrize(
    ("model_score", "reported", "expected"),
    [
        (1.0, ["A"], 1 / 3),
        (0.0, ["A", "B", "C"], 1.0),
        (0.9, ["A", "B", "invented"], 2 / 3),
    ],
)
def test_score_is_derived_from_expected_key_points(
    model_score: float, reported: list[str], expected: float
) -> None:
    output = EvaluationOutput(
        score=model_score,
        key_points_found=reported,
        missing=[],
        error_type="knowledge",
        confidence=0.9,
        feedback="Bien joué, continue !",
    )

    evaluation = to_evaluation(output, ["A", "B", "C"])

    assert evaluation is not None
    assert evaluation.score == pytest.approx(expected)
    assert evaluation.key_points_found == [point for point in ["A", "B", "C"] if point in reported]


def test_evaluation_rejects_confidence_outside_its_contract() -> None:
    output = EvaluationOutput(
        score=0.5,
        key_points_found=["A"],
        missing=["B"],
        error_type="knowledge",
        confidence=1.5,
        feedback="Bien joué, continue !",
    )

    assert to_evaluation(output, ["A", "B"]) is None



@pytest.mark.parametrize("invalid_score", [float("nan"), float("inf"), -0.1, 1.1])
def test_evaluation_rejects_non_finite_or_out_of_range_scores(invalid_score: float) -> None:
    output = EvaluationOutput(
        score=invalid_score,
        key_points_found=["A"],
        missing=["B"],
        error_type="knowledge",
        confidence=0.9,
        feedback="Bien joué, continue !",
    )

    assert to_evaluation(output, ["A", "B"]) is None


@pytest.mark.parametrize("invalid_confidence", [float("nan"), float("inf"), -0.1])
def test_evaluation_rejects_non_finite_or_negative_confidence(invalid_confidence: float) -> None:
    output = EvaluationOutput(
        score=0.5,
        key_points_found=["A"],
        missing=["B"],
        error_type="knowledge",
        confidence=invalid_confidence,
        feedback="Bien joué, continue !",
    )

    assert to_evaluation(output, ["A", "B"]) is None


def test_evaluation_without_key_points_preserves_validated_score() -> None:
    output = EvaluationOutput(
        score=0.5,
        key_points_found=[],
        missing=[],
        error_type=None,
        confidence=0.9,
        feedback="Ta réponse mérite un retour.",
    )

    evaluation = to_evaluation(output, [])

    assert evaluation is not None
    assert evaluation.score == 0.5
