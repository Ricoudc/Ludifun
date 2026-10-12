"""Assistant parent (§46) : des réponses calculées à partir des données réelles, sans IA, qui
disent sur quoi elles s'appuient, et sans jamais deviner le genre de l'enfant."""

import re

from app.domain.errors import ErrorType
from app.domain.parent_assistant import (
    AssistantFacts,
    ExamFact,
    NotionFact,
    Question,
    answers,
    exam_ready,
    how_to_help,
    progress,
    to_strengthen,
    week_focus,
)

FRACTIONS = NotionFact("Comparer des fractions", "Les fractions", 5, 2, days_since=2, subject="math")
DENOMINATOR = NotionFact("Dénominateur", "Les fractions", 3, 3, days_since=1, missing=2, subject="math")
DATES = NotionFact("1789", "La Révolution", 5, 4, days_since=30, fading=True, subject="history")
SOLID = NotionFact("Louis XVI", "La Révolution", 4, 5, days_since=1, subject="history")
NEW = NotionFact("Bastille", "La Révolution", 5, 0)


def facts(**changes: object) -> AssistantFacts:
    base: dict[str, object] = {
        "name": "Emma",
        "grade": "CM1",
        "notions": [FRACTIONS, DENOMINATOR, DATES, SOLID, NEW],
        "days_active": 2,
        "minutes": 25,
        "sessions": 2,
    }
    base.update(changes)
    return AssistantFacts(**base)  # type: ignore[arg-type]


def test_the_week_focus_comes_from_real_results() -> None:
    answer = week_focus(facts())
    # Fragile, importante : d'abord ; puis l'oubliée ; jamais une notion pas encore travaillée.
    assert answer.lines[0] == "🎯 En priorité : « Comparer des fractions » (Les fractions), fragile."
    assert "Ensuite : « 1789 » et « Dénominateur »." in answer.lines
    assert "« Bastille »" not in " ".join(answer.lines)
    assert answer.lines[-1].startswith("👉 Je recommande 3 séances courtes de 15 min")
    assert "Révisé 2 jours sur 7 (25 min)" in answer.based_on
    # La matière choisie par le parent passe devant.
    first = to_strengthen(facts(priority_subject="history"))[0]
    assert first.label == "1789"
    assert (
        week_focus(facts(priority_subject="history"))
        .lines[0]
        .endswith("maîtrisée mais pas revue depuis 30 jours.")
    )


def test_a_missing_level_says_what_is_left_to_learn() -> None:
    answer = week_focus(facts(notions=[DENOMINATOR]))
    assert "   Emma la connaît ; il reste à la retrouver sans aide." in answer.lines


def test_nothing_worked_yet() -> None:
    answer = week_focus(facts(notions=[NEW], days_active=0, minutes=0))
    assert answer.lines[0].startswith("Pas encore assez de séances")
    assert "🎯 Pour commencer : « Bastille »." in answer.lines


def test_help_at_home_depends_on_age_and_errors() -> None:
    recurring = [(ErrorType.READING, "Comparer des fractions"), (ErrorType.CALCULATION, "Dénominateur")]
    answer = how_to_help(facts(recurring=recurring))
    text = "\n".join(answer.lines)
    assert "faites-vous raconter ce qui a été appris" in text
    assert "faites relire la consigne à voix haute" in text and "poser le calcul" in text
    assert "« Enseigne-moi »" in text and "« Les fractions » dans « Mon cahier »" in text
    assert "lisez les consignes avec Emma" in how_to_help(facts(grade="CP")).lines[0]
    assert "s'organiser" in how_to_help(facts(grade="4e")).lines[0]


def test_is_the_child_ready_for_the_exam() -> None:
    exam = ExamFact("Contrôle de fractions", 2, [FRACTIONS, DENOMINATOR, SOLID, NEW])
    answer = exam_ready(facts(), exam)
    assert answer.lines[:4] == [
        "📅 Contrôle dans 2 jours.",
        "✅ Notions acquises : 1 sur 4.",
        "🟠 À revoir : « Comparer des fractions » et « Dénominateur ».",
        "⚪ Pas encore travaillées : « Bastille ».",
    ]
    assert answer.lines[-1].startswith("👉 Dernière ligne droite")
    assert [a.question for a in answers(facts(exams=[exam]))] == [
        Question.WEEK,
        Question.HELP,
        Question.EXAM,
        Question.PROGRESS,
    ]
    assert Question.EXAM not in [a.question for a in answers(facts())]


def test_progress_compares_weeks() -> None:
    assert (
        progress(facts(week_scores=[5.8, 6.5]))
        .lines[0]
        .startswith("📈 Oui : note moyenne des séances 6,5/10")
    )
    assert progress(facts(week_scores=[7.0, 6.0])).lines[0].startswith("📉")
    assert progress(facts(week_scores=[6.0, 6.2])).lines[0].startswith("➡️ Stable")
    assert progress(facts(week_scores=[None, None])).lines[0].startswith("Pas encore de séance terminée")
    assert "🌟 2 notions maîtrisées sur 5 en tout." in progress(facts()).lines


def test_no_answer_guesses_the_childs_gender() -> None:
    exam = ExamFact("Contrôle", 5, [FRACTIONS, DENOMINATOR, SOLID])
    every: list[str] = []
    for grade in ("CP", "CM1", "4e"):
        for notions in ([DENOMINATOR, FRACTIONS], [NEW]):
            for answer in answers(
                facts(
                    grade=grade,
                    notions=notions,
                    exams=[exam],
                    recurring=[(e, "1789") for e in ErrorType],
                    week_scores=[5.0, 6.0],
                    mastered_recently=["Louis XVI"],
                )
            ):
                every += [answer.title, *answer.lines, *answer.based_on]
    text = " ".join(every).replace("il reste", "")  # tournure impersonnelle
    found = re.findall(
        r"\b(il|elle|ils|elles|lui|seule?s?|prête?s?|prêt|content|contente|fatigué|fatiguée)\b", text
    )
    assert found == []
