"""§5.52 : bilan d'une compétence pour le parent — statut tiré du niveau du moteur, chiffres
cumulés, notion qui freine, conseil selon ce que la compétence demande et l'erreur fréquente."""

import re
from datetime import UTC, datetime, timedelta

from app.domain.knowledge import SkillVerb
from app.domain.skill_report import SkillNotion, SkillStatus, skill_report, status_of
from app.domain.state import Observation, notion_state
from app.domain.understanding import MasteryLevel, NotionLevel

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def notion(label: str, level: MasteryLevel, *results: tuple[float, str | None]) -> SkillNotion:
    observations = [
        Observation(T0 + timedelta(minutes=i), 2, score, score, 0, error)
        for i, (score, error) in enumerate(results)
    ]
    return SkillNotion(label, NotionLevel(level, frozenset(), ""), notion_state(observations))


def test_status_follows_the_engine_level() -> None:
    assert status_of(MasteryLevel.NEVER, observed=False) is SkillStatus.NOT_STARTED
    assert status_of(MasteryLevel.NEVER, observed=True) is SkillStatus.TO_WORK
    assert status_of(MasteryLevel.FRAGILE, observed=True) is SkillStatus.TO_WORK
    assert status_of(MasteryLevel.LEARNING, observed=True) is SkillStatus.IN_PROGRESS
    assert status_of(MasteryLevel.MASTERED, observed=True) is SkillStatus.ACQUIRED
    assert status_of(MasteryLevel.SOLID, observed=True) is SkillStatus.ACQUIRED


def test_weakest_notion_and_advice_by_verb_and_error() -> None:
    report = skill_report(
        SkillVerb.APPLY,
        MasteryLevel.FRAGILE,
        [
            notion("Numérateur", MasteryLevel.MASTERED, (1, None), (1, None)),
            notion("Comparer deux fractions", MasteryLevel.FRAGILE, (0, "calculation"), (0, "calculation")),
            notion("Dénominateur", MasteryLevel.FRAGILE, (1, None), (0.5, None)),
        ],
    )
    assert report.status is SkillStatus.TO_WORK
    assert report.weakest == "Comparer deux fractions"  # à égalité de niveau : la plus ratée
    assert (
        report.facts
        == "Sur les 6 dernières activités de ses notions : 3 réussies seul, 1 à moitié, 2 ratées."
    )
    assert report.advice is not None
    assert report.advice.startswith("Proposez un petit exercice où il faut se servir de « Comparer")
    assert report.advice.endswith("poser l'opération et vérifier aide.")


def test_acquired_or_not_started_gives_no_advice() -> None:
    done = skill_report(
        SkillVerb.RECALL, MasteryLevel.MASTERED, [notion("1789", MasteryLevel.MASTERED, (1, None))]
    )
    assert done.status is SkillStatus.ACQUIRED and done.advice is None and done.weakest is None
    assert done.summary.startswith("Acquise")
    fresh = skill_report(SkillVerb.RECALL, MasteryLevel.NEVER, [notion("1789", MasteryLevel.NEVER)])
    assert fresh.status is SkillStatus.NOT_STARTED and fresh.facts is None and fresh.advice is None


def test_a_single_error_is_not_a_pattern() -> None:
    report = skill_report(
        SkillVerb.RECALL,
        MasteryLevel.LEARNING,
        [notion("Bastille", MasteryLevel.LEARNING, (1, None), (0, "reading"), (1, None))],
    )
    assert report.status is SkillStatus.IN_PROGRESS
    assert (
        report.advice
        == "Faites redire « Bastille » sans regarder la leçon, aujourd'hui puis dans trois jours."
    )


def test_every_verb_has_advice_and_no_gendered_words() -> None:
    for verb in SkillVerb:
        report = skill_report(verb, MasteryLevel.FRAGILE, [notion("x", MasteryLevel.FRAGILE, (0, None))])
        assert report.advice and "« x »" in report.advice
        # « il faut » est impersonnel ; aucun pronom pour désigner l'enfant.
        assert not re.search(r"\b(elle|lui)\b|\bil\b(?! faut)", report.advice)
