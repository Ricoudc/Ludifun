from app.tools.evaluate_ocr import edit_distance, metrics, normalize_text


def test_edit_distance_counts_insertions_deletions_and_substitutions() -> None:
    assert edit_distance(list("chat"), list("chat")) == 0
    assert edit_distance(list("1789"), list("1780")) == 1
    assert edit_distance(["le", "chat"], ["le", "petit", "chat"]) == 1


def test_normalization_only_changes_unicode_and_whitespace() -> None:
    assert normalize_text("  École\n  1789  ") == "école 1789"


def test_metrics_keep_numbers_and_math_signs_critical() -> None:
    result = metrics("En 1789 : 3/4 = 0,75 m.", "En 1780 : 3/4 = 0,75 m.")
    assert result["char_errors"] == 1
    assert result["critical_token_errors"] == 1
    assert result["reference_critical_tokens"] == 7


def test_metrics_report_missing_units_and_words() -> None:
    result = metrics("La longueur est 12 cm.", "La longueur est 12.")
    assert result["word_errors"] == 1
    assert result["critical_token_errors"] == 1
