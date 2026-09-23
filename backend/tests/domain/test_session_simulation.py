"""Critère de fin de l'étape 3 : une séance complète simulée de bout en bout.

Un élève révise « La Révolution française » ; il connaît tout sauf les États
généraux (k3). On vérifie la séance, la reprise des erreurs, le bilan, la
prochaine révision, puis les séances suivantes.
"""

from datetime import UTC, datetime, timedelta

from app.domain.activities.base import BuiltActivity
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, SessionComposer, SessionKind
from app.domain.knowledge import KnowledgeUnit
from app.domain.mastery import Mastery
from app.domain.scoring import Evidence, KnowledgeStatus, SessionOutcome, evidences_from, summarize_session
from app.domain.simulated_pupil import Knows, respond
from tests.domain.conftest import ReferenceLesson

DAY_1 = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)


def play(
    registry: ActivityRegistry, activities: list[BuiltActivity], knows: Knows, replay: bool = False
) -> tuple[list[float], list[Evidence]]:
    scores, evidences = [], []
    for activity in activities:
        grade = registry.for_activity(activity).grade(activity, respond(activity, knows))
        scores.append(grade.score)
        evidences += evidences_from(activity, grade, registry, replay=replay)
    return scores, evidences


def run_session(
    composer: SessionComposer,
    units: list[KnowledgeUnit],
    masteries: dict[str, Mastery],
    now: datetime,
    knows: Knows,
    seed: int,
) -> tuple[SessionOutcome, list[BuiltActivity]]:
    registry = composer.registry
    plan = composer.compose(units, masteries, now, seed)
    main = [item.activity for item in plan.items]
    main_scores, evidences = play(registry, main, knows)

    replay = composer.replay(units, evidences, main, start_position=len(main) + 1, seed=seed)
    # Après la correction, l'élève a retenu : il réussit la reprise.
    _, replay_evidences = play(registry, [i.activity for i in replay], lambda _: True, replay=True)

    importance = {u.id: u.item.importance for u in units}
    outcome = summarize_session(main_scores, evidences + replay_evidences, masteries, importance, now)
    return outcome, [i.activity for i in replay]


def test_full_revision_journey(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    composer = SessionComposer(registry)
    units = list(history.units.values())

    # ── Jour 1 : première révision ───────────────────────────────────────────
    outcome, replay = run_session(composer, units, {}, DAY_1, knows=lambda k: k != "k3", seed=21)

    # Reprise : uniquement k3, dans un format différent de ceux ratés.
    assert [a.knowledge_ids for a in replay] == [["k3"]]
    plan = composer.compose(units, {}, DAY_1, seed=21)
    failed_types = {i.activity.type for i in plan.items if "k3" in i.activity.knowledge_ids}
    assert replay[0].type not in failed_types

    # Bilan : k3 à retravailler, tout le reste maîtrisé.
    statuses = {r.knowledge_id: r.status for r in outcome.results}
    assert statuses.pop("k3") in (KnowledgeStatus.TO_REVIEW, KnowledgeStatus.NOT_MASTERED)
    assert set(statuses.values()) == {KnowledgeStatus.MASTERED}
    assert outcome.results[0].knowledge_id == "k3"  # la plus fragile en tête
    assert 5 <= outcome.score_on_10 < 10
    assert outcome.errors == ["k3"]

    # Prochaine révision : demain, à cause de k3 (les notions maîtrisées reviennent à J+2).
    masteries = {r.knowledge_id: r.mastery for r in outcome.results}
    assert masteries["k3"].box == 1
    assert masteries["k1"].box == 2 and masteries["k1"].score == 100
    assert outcome.next_review_at == DAY_1 + timedelta(days=1)
    assert not outcome.lesson_mastered

    # ── « Revoir mes erreurs » juste après ───────────────────────────────────
    errors = composer.compose_errors(units, outcome.errors, seed=22)
    assert errors.kind is SessionKind.ERRORS
    assert {k for i in errors.items for k in i.activity.knowledge_ids} == {"k3"}
    assert len(errors.items) == 2

    # ── Jour 2 : révision centrée sur k3 et sur ce qui n'a pas été vu ────────
    day_2 = DAY_1 + timedelta(days=1)
    review = composer.compose(units, masteries, day_2, seed=23)
    assert review.kind is SessionKind.REVIEW
    assert review.items[0].activity.knowledge_ids == ["k3"]
    worked = {
        k for i in review.items if i.block in (Block.WARMUP, Block.CORE) for k in i.activity.knowledge_ids
    }
    mastered_not_due = {k for k, m in masteries.items() if m.score >= 90 and not m.is_due(day_2)}
    assert not worked & mastered_not_due  # on ne refait pas ce qui est su

    outcome_2, replay_2 = run_session(composer, units, masteries, day_2, knows=lambda _: True, seed=23)
    assert replay_2 == []  # aucune erreur, pas de reprise
    assert outcome_2.score_on_10 == 10
    assert {r.status for r in outcome_2.results} == {KnowledgeStatus.MASTERED}
    masteries |= {r.knowledge_id: r.mastery for r in outcome_2.results}
    assert masteries["k3"].box == 2
    assert masteries["k3"].score > outcome.results[0].mastery.score
