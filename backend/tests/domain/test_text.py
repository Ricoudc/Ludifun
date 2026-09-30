import pytest

from app.domain.text import (
    allowed_typos,
    compatible_natures,
    contains_words,
    damerau_levenshtein,
    fuzzy_contains,
    matches_with_typos,
    nature,
    normalize,
)


def test_normalize() -> None:
    assert normalize("  L’État, c'est MOI !  ") == "l etat c est moi"
    assert normalize("Les ___ généraux") == "les generaux"
    assert normalize("3/4") == "3/4"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1789", "year"),
        ("476", "number"),
        ("3,5", "number"),
        ("12", "number"),
        ("3/4", "fraction"),
        ("Le 14 juillet 1789", "date"),
        ("Louis XVI", "text"),
        ("100 degrés", "text"),
    ],
)
def test_nature(text: str, expected: str) -> None:
    assert nature(text) == expected


def test_compatible_natures() -> None:
    assert compatible_natures("1789", "1492")
    assert compatible_natures("1492", "476")  # année à 3 chiffres acceptée
    assert not compatible_natures("1789", "La Renaissance")
    assert not compatible_natures("3/4", "3")
    assert compatible_natures("Le 14 juillet 1789", "Le 5 mai 1789")
    assert not compatible_natures("Louis XVI", "1789")


def test_damerau_levenshtein() -> None:
    assert damerau_levenshtein("revolution", "revolution") == 0
    assert damerau_levenshtein("revolution", "revoultion") == 1  # transposition
    assert damerau_levenshtein("bastille", "bastile") == 1
    assert damerau_levenshtein("", "abc") == 3


@pytest.mark.parametrize(
    "expected, allowed",
    [("chat", 0), ("bastille", 1), ("revolution", 2), ("1789", 0), ("123456789", 0)],
)
def test_allowed_typos(expected: str, allowed: int) -> None:
    assert allowed_typos(expected) == allowed


@pytest.mark.parametrize(
    "given, expected, ok",
    [
        ("Révolution", "revolution", True),
        ("revolusion", "Révolution", True),  # 10 lettres : 2 fautes tolérées
        ("bastile", "Bastille", True),  # 8 lettres : 1 faute
        ("bastil", "Bastille", False),  # 2 fautes
        ("chot", "chat", False),  # 4 lettres : aucune faute
        ("1798", "1789", False),  # nombres exacts
        ("  Numérateur. ", "numérateur", True),
        ("", "numérateur", False),
    ],
)
def test_matches_with_typos(given: str, expected: str, ok: bool) -> None:
    assert matches_with_typos(given, expected) is ok


def test_contains_words() -> None:
    assert contains_words("Quelle année marque 1789 ?", "1789")
    assert not contains_words("Dans la fraction 3/4, quel est le numérateur ?", "3")
    assert not contains_words("La Révolution", "")


def test_fuzzy_contains_tolerates_ocr_errors() -> None:
    text = "Le 14 juiIlet 1789, le peuple de Paris prend la BastiIle."  # « l » lus comme « I »
    assert fuzzy_contains(text, "Le 14 juillet 1789, le peuple de Paris prend la Bastille")
    assert not fuzzy_contains(text, "Napoléon devient empereur en 1804")
    assert not fuzzy_contains(text, "")


def test_a_multiplication_table_is_found_whatever_the_sign() -> None:
    """Photo d'une table de multiplication : « 7 x 8 » lu sur la photo, « 7 × 8 » écrit par l'IA."""
    table = "La table de 7\n7 x 7 = 49\n7 x 8 = 56\n7x9=63"
    for excerpt in ("7 × 8 = 56", "7 * 9 = 63", "7 x 7 = 49"):
        assert fuzzy_contains(table, excerpt), excerpt
    assert not fuzzy_contains(table, "7 × 6 = 42")
    assert normalize("Max a 3 ans") == "max a 3 ans"
