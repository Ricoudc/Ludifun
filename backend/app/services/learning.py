"""Séances de révision en base : création, réponses, reprise, bilan, erreurs, mission du jour.

La logique pédagogique reste dans le domaine (composeur, activités, notation,
mémorisation) ; ce module la relie à PostgreSQL.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.activities.base import ActivityCode, BuiltActivity, Grade
from app.domain.activities.open_question import OpenQuestionActivity
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import (
    BLOCK_SIZE,
    UNGRADED_BLOCKS,
    Block,
    NothingToReview,
    PlannedItem,
    SessionComposer,
    SessionPlan,
)
from app.domain.decisions import Reason, Rule, reason
from app.domain.engagement import (
    BONUS_ACTIVITIES,
    FAILURE_BELOW,
    FAST_WRONG,
    MAX_REMEDIATIONS,
    REMEDIATION_AFTER_FAILURES,
    STRUGGLING,
    WINDOW,
    HintKind,
    bonus_offered,
    engagement_hint,
)
from app.domain.engagement import Answer as EngagementAnswer
from app.domain.errors import with_speed
from app.domain.help import ExternalHelp, HelpStep, next_help, result_with_help
from app.domain.mastery import Mastery
from app.domain.planning import Focus
from app.domain.rules import ENGINE_VERSION
from app.domain.scoring import (
    Evidence,
    KnowledgeStatus,
    SessionOutcome,
    evidence_weight,
    session_rates,
    status,
)
from app.domain.scoring import summarize_session as summarize
from app.domain.understanding import MasteryLevel, cognitive_level, notion_level
from app.services.answer_evaluation import AnswerEvaluator
from app.services.lesson_store import LessonUnits, load_masteries, load_units, save_masteries

STALE_SESSION = timedelta(hours=24)  # au-delà, une séance non terminée est abandonnée


class LessonNotReady(Exception):
    pass


class SessionClosed(Exception):
    pass


class AlreadyAnswered(Exception):
    pass


class MainNotFinished(Exception):
    pass


def new_seed() -> int:
    return secrets.randbits(62)


def activity_of(item: db.SessionItem, id_to_key: dict[uuid.UUID, str]) -> BuiltActivity:
    return BuiltActivity(
        type=ActivityCode(item.activity_type),
        difficulty=item.difficulty,
        knowledge_ids=[id_to_key[k] for k in item.knowledge_ids],
        payload=item.payload,
        solution=item.solution,
    )


async def session_items(session: AsyncSession, revision: db.RevisionSession) -> list[db.SessionItem]:
    result = await session.scalars(
        select(db.SessionItem)
        .where(db.SessionItem.session_id == revision.id)
        .order_by(db.SessionItem.position)
    )
    return list(result)


async def attempts_by_item(
    session: AsyncSession, revision: db.RevisionSession
) -> dict[uuid.UUID, db.Attempt]:
    result = await session.scalars(
        select(db.Attempt)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .where(db.SessionItem.session_id == revision.id)
    )
    return {a.session_item_id: a for a in result}


def _persist_plan(
    session: AsyncSession,
    revision: db.RevisionSession,
    planned: list[PlannedItem],
    lesson: LessonUnits,
    intro: str | None = None,
) -> None:
    """`intro` : texte affiché avant la première activité (rappel de la règle, remédiation)."""
    for index, item in enumerate(planned):
        session.add(
            db.SessionItem(
                session_id=revision.id,
                position=item.position,
                block=item.block.value,
                activity_type=item.activity.type.value,
                difficulty=item.activity.difficulty,
                cognitive_level=cognitive_level(item.activity.type, item.activity.difficulty),
                knowledge_ids=[lesson.key_to_id[k] for k in item.activity.knowledge_ids],
                payload=item.activity.payload,
                solution=item.activity.solution,
                intro=intro if index == 0 else None,
                reason=item.reason or None,
            )
        )


def log_decision(revision: db.RevisionSession, decision: Reason, **context: object) -> None:
    """Décision prise pendant la séance (remédiation, pause, défis bonus), avec sa raison (§126)."""
    revision.decisions = [*revision.decisions, {**decision, **context}]  # nouvelle liste : JSONB modifié


async def _new_session(
    session: AsyncSession,
    child_id: uuid.UUID,
    lesson: LessonUnits,
    plan: SessionPlan,
    seed: int,
    now: datetime,
    parent_session_id: uuid.UUID | None = None,
) -> db.RevisionSession:
    revision = db.RevisionSession(
        started_at=now,
        child_id=child_id,
        lesson_id=lesson.lesson.id,
        kind=plan.kind.value,
        parent_session_id=parent_session_id,
        status="active",
        objective=lesson.lesson.objective or lesson.lesson.title or "Réviser la leçon",
        estimated_duration_s=plan.estimated_duration_s,
        seed=seed,
        engine_version=ENGINE_VERSION,
    )
    session.add(revision)
    await session.flush()
    _persist_plan(session, revision, plan.items, lesson)
    await session.flush()
    return revision


# --------------------------------------------------------------------------- #
# Création
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionOptions:
    """Réglages venus des objectifs du parent (étape 16)."""

    core_size: int = BLOCK_SIZE  # selon le temps de révision par jour
    focus: Focus | None = None  # étape du plan avant un contrôle


def compose_with(
    composer: SessionComposer,
    lesson: LessonUnits,
    masteries: dict[str, Mastery],
    now: datetime,
    seed: int,
    options: SessionOptions,
) -> SessionPlan:
    """« Revoir tes erreurs » : les notions pas encore maîtrisées seulement ; « mini-contrôle » :
    toute la leçon, même ce qui est su. Peut lever NothingToReview."""
    units = lesson.units
    if options.focus is Focus.ERRORS:
        weak = [
            u
            for u in units
            if MasteryLevel.DISCOVERED
            <= notion_level(masteries.get(u.id), lesson.required[u.id]).level
            <= MasteryLevel.LEARNING
        ]
        units = weak or units
    return composer.compose(
        units,
        masteries,
        now,
        seed,
        core_size=options.core_size,
        include_known=options.focus is Focus.MOCK_TEST,
    )


async def start_session(
    session: AsyncSession,
    child_id: uuid.UUID,
    lesson_row: db.Lesson,
    registry: ActivityRegistry,
    now: datetime,
    options: SessionOptions | None = None,
) -> db.RevisionSession:
    """Séance adaptée à la maîtrise actuelle ; reprend une séance en cours de moins de 24 h."""
    if lesson_row.status != "ready":
        raise LessonNotReady
    # Deux demandes simultanées (double appui) : la seconde attend la première et reprend sa séance.
    await session.execute(select(db.Child.id).where(db.Child.id == child_id).with_for_update(key_share=True))
    active = await session.scalar(
        select(db.RevisionSession).where(
            db.RevisionSession.child_id == child_id,
            db.RevisionSession.lesson_id == lesson_row.id,
            db.RevisionSession.status == "active",
            db.RevisionSession.kind != "errors",
        )
    )
    if active is not None:
        if now - active.started_at < STALE_SESSION:
            return active
        active.status = "abandoned"

    lesson = await load_units(session, lesson_row)
    masteries = await load_masteries(session, child_id, lesson)
    seed = new_seed()
    plan = compose_with(SessionComposer(registry), lesson, masteries, now, seed, options or SessionOptions())
    return await _new_session(session, child_id, lesson, plan, seed, now)


async def start_errors_session(
    session: AsyncSession, origin: db.RevisionSession, registry: ActivityRegistry, now: datetime
) -> db.RevisionSession:
    """« Revoir mes erreurs » : les notions non maîtrisées de la séance d'origine (§8.4)."""
    if origin.status != "completed":
        raise SessionClosed
    already = await session.scalar(
        select(db.RevisionSession).where(
            db.RevisionSession.parent_session_id == origin.id, db.RevisionSession.status == "active"
        )
    )
    if already is not None:  # double appui sur « Revoir mes erreurs »
        return already
    lesson_row = await session.get(db.Lesson, origin.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    rates = session_rates(await load_evidences(session, origin, lesson.id_to_key))
    weak = sorted(
        (k for k, rate in rates.items() if status(rate) is not KnowledgeStatus.MASTERED),
        key=lambda k: (rates[k], -lesson.importance.get(k, 0)),
    )
    seed = new_seed()
    plan = SessionComposer(registry).compose_errors(lesson.units, weak, seed)  # peut lever NothingToReview
    return await _new_session(session, origin.child_id, lesson, plan, seed, now, parent_session_id=origin.id)


# --------------------------------------------------------------------------- #
# Réponses
# --------------------------------------------------------------------------- #


async def answer(
    session: AsyncSession,
    revision: db.RevisionSession,
    item: db.SessionItem,
    response: dict[str, Any],
    duration_ms: int | None,
    registry: ActivityRegistry,
    now: datetime,
    evaluator: AnswerEvaluator | None = None,
) -> Grade | None:
    """Corrige et enregistre une réponse. `{"skipped": true}` : activité inconnue de l'application,
    enregistrée sans compter dans la note ni dans la maîtrise (§14.3). Renvoie None dans ce cas.

    Question ouverte : corrigée par `evaluator` (IA) s'il est fourni et répond, sinon par ses
    mots clés. Pour la maîtrise, le résultat tient compte de l'aide demandée avant la réponse,
    et chaque notion ratée reçoit un type d'erreur (§5.5)."""
    if revision.status != "active":
        raise SessionClosed
    if await session.scalar(select(db.Attempt.id).where(db.Attempt.session_item_id == item.id)):
        raise AlreadyAnswered
    if response == {"skipped": True}:
        session.add(
            db.Attempt(
                session_item_id=item.id, response=response, score=0, duration_ms=duration_ms, created_at=now
            )
        )
        return None

    id_to_key = dict(await _key_map(session, revision.lesson_id))
    activity = activity_of(item, id_to_key)
    activity_type = registry.for_activity(activity)
    grade: Grade | None = None
    if isinstance(activity_type, OpenQuestionActivity) and evaluator is not None:
        text = activity_type.answer_text(response)  # peut lever InvalidResponse
        if text:
            grade = await _evaluate(session, revision, activity_type, activity, response, text, evaluator)
    if grade is None:
        grade = activity_type.grade(activity, response)  # peut lever InvalidResponse
    attempt = db.Attempt(
        session_item_id=item.id,
        response=response,
        score=round(grade.score, 2),
        duration_ms=duration_ms,
        created_at=now,
    )
    session.add(attempt)
    await session.flush()
    weight = evidence_weight(activity.type, activity.difficulty, registry)
    key_to_id = {key: knowledge_id for knowledge_id, key in id_to_key.items()}
    for key, result in grade.evidence.items():
        error = grade.errors.get(key)
        if error is not None and item.help_level == 0 and not activity_type.multi_knowledge:
            error = with_speed(error, duration_ms)
        session.add(
            db.AttemptEvidence(
                attempt_id=attempt.id,
                knowledge_id=key_to_id[key],
                result=round(result_with_help(result, item.help_level), 2),
                weight=round(weight, 2),
                error_type=error,
            )
        )
    return grade


async def _evaluate(
    session: AsyncSession,
    revision: db.RevisionSession,
    activity_type: OpenQuestionActivity,
    activity: BuiltActivity,
    response: dict[str, Any],
    text: str,
    evaluator: AnswerEvaluator,
) -> Grade | None:
    """Correction par l'IA, journalisée dans ai_runs ; None si elle n'a pas abouti."""
    lesson = await session.get(db.Lesson, revision.lesson_id)
    child = await session.get(db.Child, revision.child_id)
    grade_label = (lesson.grade if lesson else None) or (child.grade if child else "CM1")
    s = activity.solution
    done = await evaluator.evaluate(
        prompt=activity.payload["prompt"],
        key_points=s["key_points"],
        model_answer=s["model_answer"],
        answer=text,
        grade=grade_label,
    )
    run = done.run
    session.add(
        db.AiRun(
            lesson_id=revision.lesson_id,
            stage=run.stage,
            provider=run.provider,
            model=run.model,
            prompt_version=run.prompt_version,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            latency_ms=run.latency_ms,
            status=run.status,
            warnings=run.warnings[:10],
        )
    )
    if done.evaluation is None:
        return None
    return activity_type.grade_with(activity, response, done.evaluation)


# --------------------------------------------------------------------------- #
# « Je n'ai pas compris »
# --------------------------------------------------------------------------- #


class HelpUnavailable(Exception):
    pass


async def request_help(
    session: AsyncSession, revision: db.RevisionSession, item: db.SessionItem, registry: ActivityRegistry
) -> HelpStep:
    """Aide suivante pour une activité pas encore répondue ; le niveau atteint est enregistré."""
    if revision.status != "active":
        raise SessionClosed
    if await session.scalar(select(db.Attempt.id).where(db.Attempt.session_item_id == item.id)):
        raise AlreadyAnswered
    if registry.get(item.activity_type).multi_knowledge:
        raise HelpUnavailable
    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    activity = activity_of(item, lesson.id_to_key)
    unit = next(u for u in lesson.units if u.id == activity.knowledge_ids[0])
    stored = await session.scalar(
        select(db.KnowledgeItem.external_help).where(db.KnowledgeItem.id == lesson.key_to_id[unit.id])
    )
    external = None
    if stored and stored.get("text") and stored.get("sources"):
        external = ExternalHelp(str(stored["text"]), str(stored["sources"][0]["site"]))
    step = next_help(unit, activity, item.help_level, external)
    item.help_level = step.level
    return step


async def _key_map(session: AsyncSession, lesson_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    rows = await session.execute(
        select(db.KnowledgeItem.id, db.KnowledgeItem.key).where(db.KnowledgeItem.lesson_id == lesson_id)
    )
    return [(row[0], row[1]) for row in rows]


async def load_evidences(
    session: AsyncSession, revision: db.RevisionSession, id_to_key: dict[uuid.UUID, str]
) -> list[Evidence]:
    rows = await session.execute(
        select(
            db.AttemptEvidence.knowledge_id,
            db.AttemptEvidence.result,
            db.AttemptEvidence.weight,
            db.SessionItem.activity_type,
            db.SessionItem.block,
            db.SessionItem.cognitive_level,
            db.SessionItem.help_level,
        )
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .where(db.SessionItem.session_id == revision.id)
        .order_by(db.SessionItem.position)
    )
    return [
        Evidence(
            id_to_key[k],
            float(result),
            float(weight),
            ActivityCode(kind),
            block == Block.REPLAY,
            level,
            help_level,
        )
        for k, result, weight, kind, block, level, help_level in rows
    ]


# --------------------------------------------------------------------------- #
# Reprise des erreurs et bilan
# --------------------------------------------------------------------------- #


async def add_replay(
    session: AsyncSession, revision: db.RevisionSession, registry: ActivityRegistry
) -> list[db.SessionItem]:
    """Bloc « reprise des erreurs », une seule fois, après les activités principales."""
    if revision.status != "active":
        raise SessionClosed
    items = await session_items(session, revision)
    existing = [i for i in items if i.block == Block.REPLAY]
    if existing or revision.kind == "errors":
        return existing
    attempts = await attempts_by_item(session, revision)
    if any(i.id not in attempts for i in items):
        raise MainNotFinished

    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    id_to_key = lesson.id_to_key
    evidences = await load_evidences(session, revision, id_to_key)
    previous = [activity_of(i, id_to_key) for i in items]
    planned = SessionComposer(registry).replay(
        lesson.units, evidences, previous, start_position=len(items) + 1, seed=revision.seed
    )
    _persist_plan(session, revision, planned, lesson)
    await session.flush()
    return [i for i in await session_items(session, revision) if i.block == Block.REPLAY]


@dataclass(frozen=True)
class CompletedSession:
    outcome: SessionOutcome
    lesson: LessonUnits
    previous: dict[str, Mastery]  # maîtrises avant la séance (récompenses, étape 20)


async def complete(session: AsyncSession, revision: db.RevisionSession, now: datetime) -> CompletedSession:
    """Clôture : note sur 10, statut par notion, nouvelles maîtrises et prochaine révision (§9, §10)."""
    if revision.status != "active":
        raise SessionClosed
    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    items = {i.id: i for i in await session_items(session, revision)}
    main_scores = [
        float(a.score)
        for item_id, a in (await attempts_by_item(session, revision)).items()
        if items[item_id].block not in UNGRADED_BLOCKS and a.response != {"skipped": True}
    ]
    evidences = await load_evidences(session, revision, lesson.id_to_key)
    masteries = await load_masteries(session, revision.child_id, lesson)
    outcome = summarize(main_scores, evidences, masteries, lesson.importance, now, lesson.required)
    await save_masteries(
        session, revision.child_id, lesson, {r.knowledge_id: r.mastery for r in outcome.results}
    )
    revision.status, revision.completed_at = "completed", now
    revision.score_on_10 = Decimal(str(outcome.score_on_10))
    return CompletedSession(outcome, lesson, masteries)


# --------------------------------------------------------------------------- #
# Mission du jour (écran 1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mission:
    lesson: db.Lesson
    reason: Literal["exam", "due", "not_mastered", "latest"]
    estimated_minutes: int
    focus: Focus | None = None


async def mission_of_the_day(
    session: AsyncSession,
    child_id: uuid.UUID,
    registry: ActivityRegistry,
    now: datetime,
    options: SessionOptions | None = None,
    priority_subject: str | None = None,
    planned: tuple[db.Lesson, Focus] | None = None,
) -> Mission | None:
    """La révision la plus utile maintenant : l'étape du jour d'un plan avant un contrôle, puis
    notions dues, puis leçon pas encore maîtrisée, puis dernière leçon ajoutée ; à chaque fois,
    la matière choisie par le parent d'abord. Une leçon sans rien à réviser n'est jamais proposée."""
    composer = SessionComposer(registry)
    options = options or SessionOptions()

    async def estimate(lesson_row: db.Lesson, focus: Focus | None = None) -> int | None:
        lesson = await load_units(session, lesson_row)
        masteries = await load_masteries(session, child_id, lesson)
        chosen = SessionOptions(options.core_size, focus)
        try:
            plan = compose_with(composer, lesson, masteries, now, 0, chosen)
        except NothingToReview:
            return None
        return plan.estimated_minutes

    def first_priority(lessons: list[db.Lesson]) -> list[db.Lesson]:
        return sorted(lessons, key=lambda lesson: lesson.subject != priority_subject)

    if planned is not None:
        lesson_row, focus = planned
        if (minutes := await estimate(lesson_row, focus)) is not None:
            return Mission(lesson_row, "exam", minutes, focus)

    due = await session.execute(
        select(db.KnowledgeItem.lesson_id, func.min(db.KnowledgeMastery.next_review_at).label("due"))
        .join(db.KnowledgeMastery, db.KnowledgeMastery.knowledge_id == db.KnowledgeItem.id)
        .where(db.KnowledgeMastery.child_id == child_id, db.KnowledgeMastery.next_review_at <= now)
        .group_by(db.KnowledgeItem.lesson_id)
        .order_by("due")
    )
    due_lessons = [row for lesson_id, _ in due if (row := await session.get(db.Lesson, lesson_id))]
    for lesson_row in first_priority(due_lessons):
        if lesson_row.status == "ready" and (minutes := await estimate(lesson_row)):
            return Mission(lesson_row, "due", minutes)

    recent = await session.scalars(
        select(db.Lesson)
        .where(db.Lesson.child_id == child_id, db.Lesson.status == "ready")
        .order_by(db.Lesson.created_at.desc())
        .limit(20)
    )
    for lesson_row in first_priority(list(recent)):
        practised = await session.scalar(
            select(func.count())
            .select_from(db.KnowledgeMastery)
            .join(db.KnowledgeItem, db.KnowledgeItem.id == db.KnowledgeMastery.knowledge_id)
            .where(db.KnowledgeMastery.child_id == child_id, db.KnowledgeItem.lesson_id == lesson_row.id)
        )
        if (minutes := await estimate(lesson_row)) is not None:
            return Mission(lesson_row, "not_mastered" if practised else "latest", minutes)
    return None


# --------------------------------------------------------------------------- #
# Adaptation en temps réel (étape 17)
# --------------------------------------------------------------------------- #

MAIN_BLOCKS = (Block.WARMUP, Block.CORE, Block.MATCH, Block.SPEED)


@dataclass(frozen=True)
class Adaptation:
    inserted: list[db.SessionItem]  # à jouer tout de suite après l'activité répondue
    hint: HintKind | None


async def adapt(
    session: AsyncSession,
    revision: db.RevisionSession,
    item: db.SessionItem,
    grade: Grade | None,
    registry: ActivityRegistry,
) -> Adaptation:
    """Après une réponse : remédiation si une notion est ratée pour la deuxième fois dans la
    séance, et proposition de pause si l'enfant répond au hasard ou n'y arrive plus."""
    await session.flush()
    inserted: list[db.SessionItem] = []
    if grade is not None and item.block in MAIN_BLOCKS and revision.kind != "errors":
        inserted = await _remediate(session, revision, item, grade, registry)

    answers = [
        EngagementAnswer(float(score), duration)
        for score, duration, response in await session.execute(
            select(db.Attempt.score, db.Attempt.duration_ms, db.Attempt.response)
            .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
            .where(db.SessionItem.session_id == revision.id)
            .order_by(db.Attempt.created_at, db.SessionItem.position)
        )
        if response != {"skipped": True}
    ]
    since = None if revision.hint_at_answer is None else len(answers) - revision.hint_at_answer
    hint = engagement_hint(answers, since)
    if hint is not None:
        revision.hint_at_answer = len(answers)
        if hint is HintKind.FAST_GUESSING:
            why = reason(Rule.PAUSE_FAST_GUESSING, fast_wrong=FAST_WRONG, window=WINDOW)
        else:
            why = reason(Rule.PAUSE_STRUGGLING, failures=STRUGGLING)
        log_decision(revision, why, after_answers=len(answers), position=item.position)
    return Adaptation(inserted, hint)


async def _remediate(
    session: AsyncSession,
    revision: db.RevisionSession,
    item: db.SessionItem,
    grade: Grade,
    registry: ActivityRegistry,
) -> list[db.SessionItem]:
    failing_now = [k for k, result in grade.evidence.items() if result < FAILURE_BELOW]
    if not failing_now:
        return []
    items = await session_items(session, revision)
    remediated = {k for i in items if i.block == Block.REMEDIATION for k in i.knowledge_ids}
    if len(remediated) >= MAX_REMEDIATIONS:
        return []
    failures: dict[uuid.UUID, int] = {}
    rows = await session.execute(
        select(db.AttemptEvidence.knowledge_id, db.AttemptEvidence.result, db.Attempt.score, db.SessionItem)
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .where(db.SessionItem.session_id == revision.id)
    )
    for knowledge_id, result, score, row in rows:
        # Le résultat pour la maîtrise est réduit par l'aide ; ici, seul l'échec réel compte.
        raw = float(score) if row.help_level > 0 else float(result)
        if row.block in MAIN_BLOCKS and raw < FAILURE_BELOW:
            failures[knowledge_id] = failures.get(knowledge_id, 0) + 1

    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    for key in failing_now:
        knowledge_id = lesson.key_to_id[key]
        if failures.get(knowledge_id, 0) != REMEDIATION_AFTER_FAILURES or knowledge_id in remediated:
            continue
        unit = next(u for u in lesson.units if u.id == key)
        previous = [activity_of(i, lesson.id_to_key) for i in items]
        planned = SessionComposer(registry).remediation(unit, previous, item.position + 1, revision.seed)
        if not planned:
            return []
        await _shift_after(session, revision, item.position, len(planned))
        _persist_plan(session, revision, planned, lesson, intro=f"📖 Rappel : {unit.item.statement}")
        log_decision(revision, planned[0].reason, position=item.position, notion=unit.item.label)
        await session.flush()
        positions = {p.position for p in planned}
        return [i for i in await session_items(session, revision) if i.position in positions]
    return []


async def _shift_after(session: AsyncSession, revision: db.RevisionSession, position: int, by: int) -> None:
    """Décale les activités suivantes pour faire place aux activités insérées (en deux temps,
    pour ne jamais violer l'unicité de la position)."""
    later = db.SessionItem.session_id == revision.id
    await session.execute(
        update(db.SessionItem)
        .where(later, db.SessionItem.position > position)
        .values(position=-(db.SessionItem.position + by))
    )
    await session.execute(
        update(db.SessionItem)
        .where(later, db.SessionItem.position < 0)
        .values(position=-db.SessionItem.position)
    )


async def bonus_offer(session: AsyncSession, revision: db.RevisionSession) -> bool:
    """« Encore 3 défis ? » : séance bien réussie, nettement plus vite que prévu, sans reprise."""
    if revision.status != "active" or revision.extended or revision.kind == "errors":
        return False
    items = {i.id: i for i in await session_items(session, revision)}
    attempts = await attempts_by_item(session, revision)
    if set(attempts) != set(items) or any(i.block == Block.REPLAY for i in items.values()):
        return False
    main = [
        attempts[i.id]
        for i in items.values()
        if i.block in MAIN_BLOCKS and attempts[i.id].response != {"skipped": True}
    ]
    answered_ms = sum(a.duration_ms or 0 for a in main)
    return bonus_offered([float(a.score) for a in main], answered_ms, revision.estimated_duration_s)


async def extend(
    session: AsyncSession, revision: db.RevisionSession, registry: ActivityRegistry
) -> list[db.SessionItem]:
    """Défis bonus, une fois par séance, après toutes les activités (hors note, comptés pour la maîtrise)."""
    if revision.status != "active":
        raise SessionClosed
    items = await session_items(session, revision)
    if revision.extended:
        return [i for i in items if i.block == Block.BONUS]
    attempts = await attempts_by_item(session, revision)
    if any(i.id not in attempts for i in items):
        raise MainNotFinished
    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    masteries = await load_masteries(session, revision.child_id, lesson)
    previous = [activity_of(i, lesson.id_to_key) for i in items]
    start = max((i.position for i in items), default=0) + 1
    main = [float(attempts[i.id].score) for i in items if i.block in MAIN_BLOCKS]
    average = sum(main) / len(main) if main else None
    planned = SessionComposer(registry).bonus(
        lesson.units, masteries, previous, start, revision.seed, count=BONUS_ACTIVITIES, average=average
    )
    _persist_plan(session, revision, planned, lesson)
    if planned:
        log_decision(revision, planned[0].reason, position=start)
    revision.extended = True
    await session.flush()
    return [i for i in await session_items(session, revision) if i.block == Block.BONUS]
