"""Étape 24c : une année lue de travers sur la photo (1798 au lieu de 1789) est repérée grâce aux
sources, prudemment ; l'enfant vérifie sans qu'on lui souffle la réponse."""

from app.domain.reading_check import YearDoubt, doubtful_years, review_items, years

VIKIDIA = "Les États généraux se réunissent à Versailles le 5 mai 1789. La Révolution commence."
WIKIPEDIA = "En 1789, Louis XVI convoque les États généraux ; en 1799, Bonaparte prend le pouvoir."
LUMNI = "Face à la crise, Louis XVI convoque les États généraux en 1789."


def test_years_are_whole_numbers_only() -> None:
    assert years("En 1789, puis 1799 ; pas 17890 ni 3,1789 ni 12345.") == {"1789", "1799"}


def test_a_year_read_wrong_is_doubted_when_sources_agree() -> None:
    assert doubtful_years(["1798"], [VIKIDIA, WIKIPEDIA, LUMNI]) == [YearDoubt("1798", "1789")]
    assert doubtful_years(["1879"], [VIKIDIA, LUMNI]) == [YearDoubt("1879", "1789")]  # chiffre changé


def test_prudent_when_sources_do_not_settle_it() -> None:
    assert doubtful_years(["1789"], [VIKIDIA, WIKIPEDIA]) == []  # l'année lue est dans les sources
    assert doubtful_years(["1798"], [VIKIDIA]) == []  # une seule source
    assert doubtful_years(["1798"], [VIKIDIA, "En 1798, Bonaparte part en Égypte."]) == []
    assert doubtful_years(["1515"], [VIKIDIA, WIKIPEDIA]) == []  # rien de proche
    assert doubtful_years(["1798"], []) == []


def test_the_child_sees_the_sentence_not_the_expected_year() -> None:
    page = "Chapitre 3 — La Révolution\nEn 1798, le roi Louis XVI réunit les États généraux à Versailles."
    (item,) = review_items([YearDoubt("1798", "1789")], [(0, "Titre"), (1, page)])
    assert (item.page_index, item.text) == (1, "1798")
    assert item.context in page and "1798" in item.context and "1789" not in item.context
    assert review_items([YearDoubt("1515", "1519")], [(0, page)]) == []  # année absente de la photo
