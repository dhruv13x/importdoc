# tests/modules/test_confidence.py


from importdoc.modules.confidence import ConfidenceCalculator


def test_confidence_calculator_empty():
    score, explanation = ConfidenceCalculator.calculate({}, 0)
    assert score == 0
    assert "Based on:" in explanation


def test_confidence_calculator_single_evidence():
    score, explanation = ConfidenceCalculator.calculate({"ast_definition": 1}, 1)
    assert score > 0
    assert "1x ast_definition (3.0)" in explanation
    assert "1 actionable suggestions" in explanation


def test_confidence_calculator_multiple_evidence():
    score, explanation = ConfidenceCalculator.calculate(
        {"ast_definition": 2, "ast_usage": 3}, 2
    )
    assert score > 0
    assert "2x ast_definition (3.0)" in explanation
    assert "3x ast_usage (2.0)" in explanation
    assert "2 actionable suggestions" in explanation
