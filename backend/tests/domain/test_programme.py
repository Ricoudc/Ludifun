"""Programme officiel par classe (§105) : le référentiel est complet et cohérent, et le code range
chaque notion d'une leçon dans la bonne sous-compétence."""

import json

import pytest

from app.domain.knowledge import Grade, Subject
from app.domain.programme import PROGRAMME_FILE, load_programme, place

PROGRAMME = load_programme()


def test_the_referential_is_consistent() -> None:
    raw = json.loads(PROGRAMME_FILE.read_text(encoding="utf-8"))
    assert raw["version"] and raw["source"]
    subs = [s for subject in PROGRAMME.subjects for s in PROGRAMME.subs(subject)]
    ids = [s.id for s in subs]
    assert len(ids) == len(set(ids)), "identifiants en double"
    assert set(PROGRAMME.subjects) <= {s.value for s in Subject} - {"other"}
    for sub in subs:
        assert sub.grades and set(sub.grades) <= {g.value for g in Grade}, sub.id
        assert len(sub.words) >= 2, sub.id
        assert sub.id.startswith({"math": "MA", "french": "FR", "history": "HI", "geography": "GE",
                                  "science": "SC", "english": "EN", "civics": "EM"}[sub.subject])  # fmt: skip


@pytest.mark.parametrize("grade", [g.value for g in Grade])
@pytest.mark.parametrize("subject", ["french", "math", "history", "geography", "science"])
def test_every_grade_has_a_programme(subject: str, grade: str) -> None:
    domains = PROGRAMME.for_grade(subject, grade)
    assert domains, f"{subject} {grade}"
    assert all(grade in s.grades for d in domains for c in d.competences for s in c.subs)


@pytest.mark.parametrize(
    "subject, grade, text, expected",
    [
        ("history", "CM1", "La Révolution française — La prise de la Bastille, le 14 juillet 1789", "HI-05"),
        ("math", "CM2", "Les fractions — Le numérateur est au-dessus du trait de fraction", "MA-07"),
        ("science", "CE2", "Les états de l'eau — La glace fond et devient de l'eau liquide", "SC-03"),
        ("french", "CE1", "Le pluriel des noms — Au pluriel, on écrit les ou des devant le nom", "FR-09"),
        ("french", "CE2", "Le nom commun et le nom propre — Un nom propre prend une majuscule", "FR-07"),
        ("french", "CM1", "Le passé composé — Il se forme avec l'auxiliaire avoir ou être", "FR-12"),
        ("geography", "CM1", "Les fleuves de France — La Loire est le plus long fleuve", "GE-03"),
        ("math", "4e", "Le théorème de Pythagore — Dans un triangle rectangle, l'hypoténuse…", "MA-35"),
        ("history", "5e", "Les croisades — Les chrétiens partent pour Jérusalem", "HI-12"),
        ("science", "6e", "La digestion — Les aliments sont transformés dans le tube digestif", "SC-09"),
        ("civics", "CM1", "La laïcité — L'école publique est laïque", "EM-02"),
    ],
)
def test_a_notion_finds_its_place(subject: str, grade: str, text: str, expected: str) -> None:
    found = place(PROGRAMME, subject, grade, text)
    assert found is not None and found.sub.id == expected and found.grade_match


def test_another_grade_or_nowhere() -> None:
    # Une leçon de CM2 vue en CM1 : rangée dans le programme de CM2, signalée comme telle.
    ahead = place(PROGRAMME, "history", "CM1", "La bataille de Verdun pendant la guerre de 1914")
    assert ahead is not None and not ahead.grade_match and "CM2" in ahead.sub.grades
    assert place(PROGRAMME, "history", "CM1", "Les pingouins de l'Antarctique") is None
    assert place(PROGRAMME, "other", "CM1", "La musique baroque") is None
    assert place(PROGRAMME, None, "CM1", "Les fractions") is None
