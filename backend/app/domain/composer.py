"""Composition d'une séance (cahier des charges §8).

Première révision : 🧠 3 activités faciles, 🎯 3 intermédiaires, 🧩 1 association,
⚡ 1 défi rapide, puis 🔄 la reprise des erreurs, ajoutée en fin de séance.
Révisions suivantes : même structure, centrée sur les notions fragiles ou dues.

Tout est déterministe pour une graine donnée : la graine est enregistrée avec la
séance, ce qui permet de rejouer exactement un problème signalé.
"""

import itertools
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeUnit
from app.domain.mastery import IMPORTANT, KNOWN_SCORE, Mastery
from app.domain.scoring import Evidence
from app.domain.text import normalize

BLOCK_SIZE = 3  # activités dans l'échauffement et dans l'approfondissement
STRONG_NOTIONS_NEEDED = 6  # en dessous, les notions d'importance ≤ 2 sont aussi utilisées
MATCH_PAIRS = (3, 5)  # 4 à 5 visées ; 3 pour les petites leçons
SPEED_NOTIONS = 5
REPLAY_MAX = 3
ERRORS_PER_NOTION = 2
EXPRESS_BELOW = 3  # moins de 3 notions à travailler : révision express
MAX_ORDERS = 720  # ordres de notions essayés pour éviter deux formats identiques à la suite

TRANSITION_S = 5
CORRECTION_S = 8
REPLAY_PROVISION_S = 0.3 * REPLAY_MAX * 20

EASY = frozenset({ActivityCode.MCQ, ActivityCode.TRUE_FALSE})
INTERMEDIATE = frozenset({ActivityCode.FILL_BLANK, ActivityCode.MCQ, ActivityCode.FLASHCARD})


# Pour une notion : difficultés préférées (dans l'ordre) et formats autorisés (None = tous).
Prefs = Callable[[KnowledgeUnit], tuple[tuple[int, ...], frozenset[ActivityCode] | None]]


class Block(StrEnum):
    WARMUP = "warmup"
    CORE = "core"
    MATCH = "match"
    SPEED = "speed"
    REPLAY = "replay"


class SessionKind(StrEnum):
    FIRST = "first"
    REVIEW = "review"
    ERRORS = "errors"


class NothingToReview(Exception):
    """Toutes les notions sont maîtrisées et aucune révision n'est due."""


@dataclass(frozen=True)
class PlannedItem:
    position: int
    block: Block
    activity: BuiltActivity


@dataclass(frozen=True)
class SessionPlan:
    kind: SessionKind
    items: list[PlannedItem]
    estimated_duration_s: int
    express: bool = False

    @property
    def estimated_minutes(self) -> int:
        return max(1, math.ceil(self.estimated_duration_s / 60))


def target_difficulties(mastery: Mastery | None) -> tuple[int, ...]:
    """Difficultés adaptées au score de maîtrise (§8.3), par ordre de préférence."""
    if mastery is None or mastery.score < 50:
        return (1,)
    if mastery.score < 80:
        return (2, 1)
    return (3, 2)


class SessionComposer:
    def __init__(self, registry: ActivityRegistry) -> None:
        self.registry = registry

    # ------------------------------------------------------------------ #
    # Séances « première révision » et « révision »
    # ------------------------------------------------------------------ #

    def compose(
        self, units: Sequence[KnowledgeUnit], masteries: Mapping[str, Mastery], now: datetime, seed: int
    ) -> SessionPlan:
        rng = random.Random(seed)
        eligible = _eligible(units)
        first = not any(u.id in masteries for u in units)
        if first:
            ranked = sorted(eligible, key=lambda u: (-u.item.importance, units.index(u)))
            to_work = ranked
        else:
            to_work = self._to_review(eligible, masteries, now, units)
            if not to_work:
                raise NothingToReview
            ranked = to_work + [u for u in eligible if u not in to_work]

        items: list[BuiltActivity] = []
        blocks: list[Block] = []

        def add(activity: BuiltActivity | None, block: Block) -> None:
            if activity is not None:
                items.append(activity)
                blocks.append(block)

        express = not first and len(to_work) < EXPRESS_BELOW
        used: dict[str, set[ActivityCode]] = {}

        # 🧠 Échauffement, puis 🎯 approfondissement.
        def prefs(block_difficulty: int, types: frozenset[ActivityCode]) -> Prefs:
            if first:
                return lambda unit: ((block_difficulty,), types)
            return lambda unit: (target_difficulties(masteries.get(unit.id)), None)

        warmup_units = to_work[:BLOCK_SIZE]
        for activity in self._sequence(warmup_units, prefs(1, EASY), items, used, rng):
            add(activity, Block.WARMUP)

        if not express:
            core_units = to_work[BLOCK_SIZE : 2 * BLOCK_SIZE]
            # Leçon courte : on reprend les notions les plus importantes, avec un autre format.
            core_units += warmup_units[: BLOCK_SIZE - len(core_units)]
            for activity in self._sequence(core_units, prefs(2, INTERMEDIATE), items, used, rng):
                add(activity, Block.CORE)

            # 🧩 Association : d'abord les notions pas encore vues dans la séance.
            seen = {k for a in items for k in a.knowledge_ids}
            candidates = [u for u in ranked if u.id not in seen] + [u for u in ranked if u.id in seen]
            add(self._match(candidates, rng), Block.MATCH)

        # ⚡ Défi rapide : les notions à travailler d'abord, complétées par les autres si besoin.
        add(self._speed(ranked, rng), Block.SPEED)

        planned = [
            PlannedItem(i, block, a) for i, (block, a) in enumerate(zip(blocks, items, strict=True), 1)
        ]
        kind = SessionKind.FIRST if first else SessionKind.REVIEW
        return SessionPlan(kind, planned, self.estimate_duration_s(items, with_replay=True), express)

    def _to_review(
        self,
        eligible: list[KnowledgeUnit],
        masteries: Mapping[str, Mastery],
        now: datetime,
        units: Sequence[KnowledgeUnit],
    ) -> list[KnowledgeUnit]:
        """Notions à travailler, par priorité : importance × fragilité, majorée si due (§8.3)."""

        def priority(unit: KnowledgeUnit) -> float:
            mastery = masteries.get(unit.id)
            score = mastery.score if mastery else 0
            due = mastery is None or mastery.is_due(now)
            return unit.item.importance * (100 - score) / 100 * (1.5 if due else 1.0)

        def known(unit: KnowledgeUnit) -> bool:
            mastery = masteries.get(unit.id)
            return mastery is not None and mastery.score >= KNOWN_SCORE and not mastery.is_due(now)

        working = [u for u in eligible if not known(u)]
        return sorted(working, key=lambda u: (-priority(u), -u.item.importance, units.index(u)))

    # ------------------------------------------------------------------ #
    # 🔄 Reprise des erreurs (fin de séance)
    # ------------------------------------------------------------------ #

    def replay(
        self,
        units: Sequence[KnowledgeUnit],
        evidences: Sequence[Evidence],
        previous: Sequence[BuiltActivity],
        start_position: int,
        seed: int,
    ) -> list[PlannedItem]:
        """Une activité par notion ratée (3 au plus), dans un format différent de celui raté."""
        rng = random.Random(f"{seed}:replay")
        by_id = {u.id: u for u in units}
        failed: dict[str, set[ActivityCode]] = {}
        worst: dict[str, float] = {}
        for e in evidences:
            if e.replay or e.knowledge_id not in by_id:
                continue
            worst[e.knowledge_id] = min(worst.get(e.knowledge_id, 1.0), e.result)
            if e.result < 0.5:
                failed.setdefault(e.knowledge_id, set()).add(e.activity_type)

        order = sorted(failed, key=lambda k: (worst[k], -by_id[k].item.importance, k))
        used = {k: set(types) for k, types in failed.items()}
        any_format: Prefs = lambda unit: ((1, 2, 3), None)  # noqa: E731
        candidates = [by_id[k] for k in order if self._options(by_id[k], (1, 2, 3), None, used, True, rng)]
        activities = self._sequence(candidates[:REPLAY_MAX], any_format, list(previous), used, rng)
        return [PlannedItem(start_position + i, Block.REPLAY, a) for i, a in enumerate(activities)]

    # ------------------------------------------------------------------ #
    # Séance « Revoir mes erreurs » (§8.4)
    # ------------------------------------------------------------------ #

    def compose_errors(
        self, units: Sequence[KnowledgeUnit], knowledge_ids: Sequence[str], seed: int
    ) -> SessionPlan:
        rng = random.Random(seed)
        by_id = {u.id: u for u in units}
        targets = [by_id[k] for k in knowledge_ids if k in by_id]
        items: list[BuiltActivity] = []
        used: dict[str, set[ActivityCode]] = {}
        # Tours successifs : notion 1, notion 2… puis deuxième format pour chacune.
        any_format: Prefs = lambda unit: ((1, 2, 3), None)  # noqa: E731
        for _ in range(ERRORS_PER_NOTION):
            items += self._sequence(targets, any_format, items, used, rng)
        if not items:
            raise NothingToReview
        planned = [PlannedItem(i, Block.CORE, a) for i, a in enumerate(items, 1)]
        return SessionPlan(SessionKind.ERRORS, planned, self.estimate_duration_s(items, with_replay=False))

    # ------------------------------------------------------------------ #
    # Outils
    # ------------------------------------------------------------------ #

    def _sequence(
        self,
        units: Sequence[KnowledgeUnit],
        prefs: Prefs,
        previous: Sequence[BuiltActivity],
        used: dict[str, set[ActivityCode]],
        rng: random.Random,
    ) -> list[BuiltActivity]:
        """Une activité par notion, sans jamais deux formats identiques à la suite (§8.1).

        On essaie d'abord les formats et difficultés préférés (dans tous les ordres
        possibles des notions), puis on assouplit la difficulté ; une répétition n'est
        acceptée qu'en dernier recours. Un format déjà utilisé pour une notion ne lui
        est plus proposé.
        """
        last = previous[-1].type if previous else None
        chain: list[tuple[KnowledgeUnit, ActivityCode, int]] | None = None
        for relaxed in (False, True):
            options = {u.id: self._options(u, *prefs(u), used, relaxed, rng) for u in units}
            playable = [u for u in units if options[u.id]]
            for order in itertools.islice(itertools.permutations(playable), MAX_ORDERS):
                chain = _chain(list(order), options, last)
                if chain is not None:
                    break
            if chain is not None:
                break
        if chain is None:
            chain = [(u, *options[u.id][0]) for u in playable]

        activities = []
        for unit, code, difficulty in chain:
            used.setdefault(unit.id, set()).add(code)
            activities.append(self.registry.get(code).build([unit], difficulty, rng))
        return activities

    def _options(
        self,
        unit: KnowledgeUnit,
        difficulties: tuple[int, ...],
        types: frozenset[ActivityCode] | None,
        used: dict[str, set[ActivityCode]],
        relaxed: bool,
        rng: random.Random,
    ) -> list[tuple[ActivityCode, int]]:
        """Formats possibles pour une notion, par ordre de préférence."""
        available = self.registry.single_options(unit)
        already = used.get(unit.id, set())
        searches = [(difficulties, types)]
        if relaxed:
            searches += [(difficulties, None), ((1, 2, 3), None)]
        result: list[tuple[ActivityCode, int]] = []
        for wanted, allowed in searches:
            for difficulty in wanted:
                codes = sorted(
                    code
                    for code, d in available
                    if d == difficulty and code not in already and (allowed is None or code in allowed)
                )
                rng.shuffle(codes)
                result += [(code, difficulty) for code in codes if (code, difficulty) not in result]
        return result

    def _match(self, candidates: list[KnowledgeUnit], rng: random.Random) -> BuiltActivity | None:
        match = self.registry.get(ActivityCode.MATCH)
        chosen: list[KnowledgeUnit] = []
        for unit in candidates:
            # On n'ajoute une notion que si l'association reste sans ambiguïté.
            if len(chosen) < MATCH_PAIRS[1] and match.accepts(unit) and _distinct_pairs([*chosen, unit]):
                chosen.append(unit)
        return match.build(chosen, 2, rng) if match.can_build(chosen, 2) else None

    def _speed(self, candidates: list[KnowledgeUnit], rng: random.Random) -> BuiltActivity | None:
        speed = self.registry.get(ActivityCode.SPEED_CHALLENGE)
        chosen = [u for u in candidates if speed.accepts(u)][:SPEED_NOTIONS]
        return speed.build(chosen, 1, rng) if chosen and speed.can_build(chosen, 1) else None

    def estimate_duration_s(self, activities: Sequence[BuiltActivity], with_replay: bool) -> int:
        """§8.2 : durées de base + transitions + corrections (+ provision pour la reprise)."""
        seconds = sum(
            self.registry.get(a.type).base_duration_s + TRANSITION_S + CORRECTION_S for a in activities
        )
        return math.ceil(seconds + (REPLAY_PROVISION_S if with_replay else 0))


def _eligible(units: Sequence[KnowledgeUnit]) -> list[KnowledgeUnit]:
    """Les notions d'importance ≤ 2 ne servent que si la leçon a moins de 6 notions importantes."""
    strong = [u for u in units if u.item.importance >= IMPORTANT]
    return strong if len(strong) >= STRONG_NOTIONS_NEEDED else list(units)


def _distinct_pairs(units: list[KnowledgeUnit]) -> bool:
    pairs = [u.material.pair for u in units if u.material.pair is not None]
    return len({normalize(p.left) for p in pairs}) == len({normalize(p.right) for p in pairs}) == len(pairs)


def _chain(
    order: list[KnowledgeUnit],
    options: Mapping[str, list[tuple[ActivityCode, int]]],
    last: ActivityCode | None,
) -> list[tuple[KnowledgeUnit, ActivityCode, int]] | None:
    """Premier enchaînement (notion, format, difficulté) sans deux formats identiques à la suite."""
    if not order:
        return []
    unit, rest = order[0], order[1:]
    for code, difficulty in options[unit.id]:
        if code != last:
            tail = _chain(rest, options, code)
            if tail is not None:
                return [(unit, code, difficulty), *tail]
    return None
