"""§5.79 : non-régression pédagogique. Une séance de référence qui change fait échouer ce test ;
si le changement est voulu, relire la différence puis
`uv run python -m app.tools.reference_sessions --update`."""

from app.tools.reference_sessions import GOLDEN, difference, render


def test_reference_sessions_are_unchanged() -> None:
    expected = GOLDEN.read_text(encoding="utf-8").rstrip("\n")
    actual = render()
    assert actual == expected, "Les séances de référence ont changé :\n" + difference(expected, actual)


def test_rendering_is_stable() -> None:
    assert render() == render()  # même code, même texte : aucun hasard non fixé
