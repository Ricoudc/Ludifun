"""Composition d'une séance (cahier des charges §8).

Première révision : 🧠 3 activités faciles, 🎯 3 intermédiaires, 🧩 1 association,
⚡ 1 défi rapide, puis 🔄 la reprise des erreurs, ajoutée en fin de séance.
Révisions suivantes : même structure, centrée sur les notions fragiles ou dues ; une notion
bien réussie mais dont un niveau de compréhension manque (se rappeler, appliquer) est
travaillée à ce niveau (spécification technique §5.1).

Tout est déterministe pour une graine donnée : la graine est enregistrée avec la
séance, ce qui permet de rejouer exactement un problème signalé.
"""

import itertools
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.activities.registry import ActivityRegistry
from app.domain.decisions import Reason, Rule, reason
from app.domain.knowledge import KnowledgeUnit
from app.domain.mastery import IMPORTANT, KNOWN_SCORE, Mastery
from app.domain.rules import RULES
from app.domain.scoring import Evidence
from app.domain.text import normalize
from app.domain.understanding import cognitive_level, required_levels

# Seuils réglés dans engine_rules.toml (§125).
BLOCK_SIZE = RULES.session.block_size
STRONG_NOTIONS_NEEDED = RULES.session.strong_notions_needed
SPEED_NOTIONS = RULES.session.speed_notions
REPLAY_MAX = RULES.session.replay_max
ERRORS_PER_NOTION = RULES.session.errors_per_notion
EXPRESS_BELOW = RULES.session.express_below
LEVEL_UP_SCORE = RULES.session.level_up_score
DEEPEN_SCORE = RULES.session.deepen_score
MISSING_LEVEL_SCORE = RULES.session.missing_level_score
VISUAL_FIRST = RULES.session.visual_first
MAX_ORDERS = 720  # ordres de notions essayés pour éviter deux formats identiques à la suite
FRESH_TRIES = 8  # tirages essayés pour trouver une question pas posée aux séances précédentes

TRANSITION_S = 5
CORRECTION_S = 8
REPLAY_PROVISION_S = 0.3 * REPLAY_MAX * 20

EASY = frozenset({ActivityCode.MCQ, ActivityCode.TRUE_FALSE})
# Une question ouverte n'est proposée que lorsqu'on vise son niveau (expliquer, transférer…) :
# jamais « par défaut », ni dans la reprise des erreurs.
ON_REQUEST = frozenset({ActivityCode.OPEN_QUESTION})
# Jeux visuels, plus agréables à faire et à voir qu'un quiz : proposés d'abord (étape 25).
VISUAL = frozenset(
    {
        ActivityCode.ORDER,
        ActivityCode.CLASSIFY,
        ActivityCode.COLORING,
        ActivityCode.SCRAMBLE,
        ActivityCode.UNJUMBLE,
    }
)
INTERMEDIATE = frozenset(
    {
        ActivityCode.FILL_BLANK,
        ActivityCode.MCQ,
        ActivityCode.FLASHCARD,
        ActivityCode.ORDER,
        ActivityCode.CLASSIFY,
        ActivityCode.COLORING,
        ActivityCode.WORD_FLASH,
        ActivityCode.SCRAMBLE,
        ActivityCode.DICTATION,
        ActivityCode.UNJUMBLE,
    }
)
# 🧩 Jeu à plusieurs notions de fin de séance : à la première séance, la carte (étape 22) si les
# notions sont sur une même figure, sinon l'association ; ensuite au choix carte, association,
# frise chronologique ou memory (étape 21), trouver la correspondance, roue, boîtes ou cartes
# aléatoires (étape 26), jeux en images (étape 28), pour varier.
PUZZLES = (
    (ActivityCode.MAP, 2),
    (ActivityCode.PICTURE_MATCH, 1),
    (ActivityCode.MATCH, 2),
    (ActivityCode.TIMELINE, 2),
    (ActivityCode.MEMORY, 1),
    (ActivityCode.FIND_MATCH, 2),
    (ActivityCode.WHEEL, 1),
    (ActivityCode.BOX, 1),
    (ActivityCode.RANDOM_CARDS, 2),
    (ActivityCode.PICTURE_FIND, 2),
)
# Première séance : la carte, sinon les images des notions validées par le parent (étape 28),
# sinon l'association.
FIRST_PUZZLES = frozenset({ActivityCode.MAP, ActivityCode.PICTURE_MATCH, ActivityCode.MATCH})


# Pour une notion : difficultés préférées (dans l'ordre) et formats autorisés (None = tous).
Prefs = Callable[[KnowledgeUnit], tuple[tuple[int, ...], frozenset[ActivityCode] | None]]


class Block(StrEnum):
    WARMUP = "warmup"
    CORE = "core"
    MATCH = "match"
    SPEED = "speed"
    REPLAY = "replay"
    REMEDIATION = "remediation"  # insérée après deux échecs sur une notion (étape 17)
    BONUS = "bonus"  # défis en plus, quand l'enfant va vite (étape 17)


# Blocs hors de la note sur 10 : on y apprend, on n'y est pas évalué.
UNGRADED_BLOCKS = frozenset({"replay", "remediation", "bonus"})


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
    reason: Reason = field(default_factory=dict)  # pourquoi cette activité (§126)


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
        self.recent: frozenset[str] = frozenset()

    # ------------------------------------------------------------------ #
    # Séances « première révision » et « révision »
    # ------------------------------------------------------------------ #

    def compose(
        self,
        units: Sequence[KnowledgeUnit],
        masteries: Mapping[str, Mastery],
        now: datetime,
        seed: int,
        core_size: int = BLOCK_SIZE,
        include_known: bool = False,
        recent: frozenset[str] = frozenset(),
    ) -> SessionPlan:
        """`core_size` : activités d'approfondissement (selon le temps du jour choisi par le parent ;
        0 : révision express). `include_known` : toute la leçon, même ce qui est su (mini-contrôle).
        `recent` : empreintes (`fingerprint`) des questions des séances précédentes de la leçon,
        évitées tant que la notion en a d'autres."""
        rng = random.Random(seed)
        self.recent = recent
        eligible = _eligible(units)
        first = not any(u.id in masteries for u in units)
        if first:
            ranked = sorted(eligible, key=lambda u: (-u.item.importance, units.index(u)))
            to_work = ranked
        else:
            to_work = self._to_review(eligible, masteries, now, units, include_known)
            if not to_work:
                raise NothingToReview
            ranked = to_work + [u for u in eligible if u not in to_work]

        items: list[BuiltActivity] = []
        blocks: list[Block] = []

        def add(activity: BuiltActivity | None, block: Block) -> None:
            if activity is not None:
                items.append(activity)
                blocks.append(block)

        express = (not first and len(to_work) < EXPRESS_BELOW) or core_size == 0
        used: dict[str, set[ActivityCode]] = {}

        # 🧠 Échauffement, puis 🎯 approfondissement.
        def prefs(block_difficulty: int, types: frozenset[ActivityCode]) -> Prefs:
            if first:
                return lambda unit: ((block_difficulty,), types)
            return lambda unit: self._review_prefs(unit, masteries.get(unit.id))

        warmup_units = to_work[:BLOCK_SIZE]
        for activity in self._sequence(warmup_units, prefs(1, EASY), items, used, rng):
            add(activity, Block.WARMUP)

        if not express:
            # Par tours de 3 notions : les suivantes à travailler, puis (leçon courte, séance longue)
            # les plus importantes à nouveau, dans un autre format.
            order = to_work[BLOCK_SIZE:] + warmup_units + [u for u in ranked if u not in to_work]
            position, done = 0, 0
            while done < core_size and order:
                round_units: list[KnowledgeUnit] = []
                while len(round_units) < min(BLOCK_SIZE, core_size - done, len(order)):
                    unit = order[position % len(order)]
                    position += 1
                    if unit not in round_units:
                        round_units.append(unit)
                activities = self._sequence(round_units, prefs(2, INTERMEDIATE), items, used, rng)
                if not activities:
                    break  # plus aucun format neuf pour ces notions
                for activity in activities:
                    add(activity, Block.CORE)
                done += len(activities)

            # 🧩 Association : d'abord les notions pas encore vues dans la séance.
            seen = {k for a in items for k in a.knowledge_ids}
            candidates = [u for u in ranked if u.id not in seen] + [u for u in ranked if u.id in seen]
            add(self._puzzle(candidates, rng, first), Block.MATCH)

        # ⚡ Défi rapide : les notions à travailler d'abord, complétées par les autres si besoin.
        add(self._speed(ranked, rng), Block.SPEED)

        by_id = {u.id: u for u in units}
        planned = [
            PlannedItem(i, block, a, _visual(a, self._reason(a, block, first, by_id, masteries, now)))
            for i, (block, a) in enumerate(zip(blocks, items, strict=True), 1)
        ]
        kind = SessionKind.FIRST if first else SessionKind.REVIEW
        return SessionPlan(kind, planned, self.estimate_duration_s(items, with_replay=True), express)

    def _reason(
        self,
        activity: BuiltActivity,
        block: Block,
        first: bool,
        by_id: Mapping[str, KnowledgeUnit],
        masteries: Mapping[str, Mastery],
        now: datetime,
    ) -> Reason:
        """La règle qui a fait choisir cette activité, et ses faits (§126)."""
        if block is Block.MATCH:
            return reason(Rule.GAME, notions=len(activity.knowledge_ids), type=activity.type.value)
        if block is Block.SPEED:
            return reason(Rule.SPEED, notions=len(activity.knowledge_ids))
        unit = by_id[activity.knowledge_ids[0]]
        mastery = masteries.get(unit.id)
        if first:
            return reason(Rule.FIRST_SESSION, importance=unit.item.importance, difficulty=activity.difficulty)
        if mastery is None:
            return reason(Rule.NEW_NOTION, difficulty=activity.difficulty)
        level = int(cognitive_level(activity.type, activity.difficulty))
        if level in self._missing(unit, mastery) and mastery.score >= LEVEL_UP_SCORE:
            return reason(Rule.LEVEL_UP, score=mastery.score, threshold=LEVEL_UP_SCORE, level=level)
        if mastery.score >= DEEPEN_SCORE and level not in required_levels(unit, self.registry):
            return reason(Rule.DEEPEN, score=mastery.score, level=level)
        return reason(
            Rule.BY_SCORE, score=mastery.score, due=mastery.is_due(now), difficulty=activity.difficulty
        )

    def _to_review(
        self,
        eligible: list[KnowledgeUnit],
        masteries: Mapping[str, Mastery],
        now: datetime,
        units: Sequence[KnowledgeUnit],
        include_known: bool = False,
    ) -> list[KnowledgeUnit]:
        """Notions à travailler, par priorité : importance × fragilité, majorée si due (§8.3). La
        fragilité part du score estimé aujourd'hui : une notion pas revue depuis longtemps remonte
        (§130)."""

        def priority(unit: KnowledgeUnit) -> float:
            mastery = masteries.get(unit.id)
            score = mastery.recall(now) if mastery else 0
            if self._missing(unit, mastery):
                score = min(score, MISSING_LEVEL_SCORE)
            due = mastery is None or mastery.is_due(now)
            return unit.item.importance * (100 - score) / 100 * (1.5 if due else 1.0)

        def known(unit: KnowledgeUnit) -> bool:
            mastery = masteries.get(unit.id)
            return (
                mastery is not None
                and mastery.score >= KNOWN_SCORE
                and not mastery.is_due(now)
                and not self._missing(unit, mastery)
            )

        working = [u for u in eligible if include_known or not known(u)]
        return sorted(working, key=lambda u: (-priority(u), -u.item.importance, units.index(u)))

    def _missing(self, unit: KnowledgeUnit, mastery: Mastery | None) -> frozenset[int]:
        """Niveaux de compréhension exigés pour la notion et pas encore validés."""
        levels = mastery.levels if mastery else frozenset()
        return required_levels(unit, self.registry) - levels

    def _review_prefs(
        self, unit: KnowledgeUnit, mastery: Mastery | None
    ) -> tuple[tuple[int, ...], frozenset[ActivityCode] | None]:
        """Révision : difficulté selon le score ; au-delà de 50, le premier niveau manquant."""
        missing = self._missing(unit, mastery)
        target: int | None = None
        if mastery is not None and mastery.score >= LEVEL_UP_SCORE and missing:
            target = min(missing)
        elif mastery is not None and mastery.score >= DEEPEN_SCORE:
            # Tous les niveaux exigés sont validés : on approfondit (expliquer, transférer).
            deeper = (
                {cognitive_level(code, difficulty) for code, difficulty in self.registry.single_options(unit)}
                - mastery.levels
                - required_levels(unit, self.registry)
            )
            target = min(deeper, default=None)
        if target is not None:
            options = [
                (code, difficulty)
                for code, difficulty in self.registry.single_options(unit)
                if cognitive_level(code, difficulty) == target
            ]
            if options:
                difficulties = tuple(sorted({d for _, d in options}, reverse=True))
                return difficulties, frozenset(code for code, _ in options)
        return target_difficulties(mastery), None

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
        # Tous les formats déjà ratés (après une remédiation, par exemple) : on en réutilise un.
        for k in order:
            if not self._options(by_id[k], (1, 2, 3), None, used, True, rng):
                used[k] = set()
        any_format: Prefs = lambda unit: ((1, 2, 3), None)  # noqa: E731
        candidates = [by_id[k] for k in order if self._options(by_id[k], (1, 2, 3), None, used, True, rng)]
        activities = self._sequence(candidates[:REPLAY_MAX], any_format, list(previous), used, rng)
        return [
            PlannedItem(
                start_position + i,
                Block.REPLAY,
                a,
                reason(
                    Rule.REPLAY,
                    result=round(worst[a.knowledge_ids[0]], 2),
                    failed=sorted(code.value for code in failed.get(a.knowledge_ids[0], set())),
                ),
            )
            for i, a in enumerate(activities)
        ]

    # ------------------------------------------------------------------ #
    # Adaptation en temps réel (étape 17)
    # ------------------------------------------------------------------ #

    def remediation(
        self,
        unit: KnowledgeUnit,
        previous: Sequence[BuiltActivity],
        start_position: int,
        seed: int,
    ) -> list[PlannedItem]:
        """Après deux échecs sur une notion : une activité facile (reconnaître), puis une autre dans
        un format pas encore raté, à insérer tout de suite (le rappel de la règle les précède)."""
        rng = random.Random(f"{seed}:remediation:{unit.id}")
        failed = {a.type for a in previous if unit.id in a.knowledge_ids}
        used = {unit.id: set(failed)}
        easy: Prefs = lambda u: ((1,), EASY)  # noqa: E731
        normal: Prefs = lambda u: ((2, 1), None)  # noqa: E731
        first = self._sequence([unit], easy, previous, used, rng)
        second = self._sequence([unit], normal, [*previous, *first], used, rng)
        why = reason(
            Rule.REMEDIATION,
            failures=RULES.adaptation.remediation_after_failures,
            failed=sorted(code.value for code in failed),
        )
        return [
            PlannedItem(start_position + i, Block.REMEDIATION, a, why)
            for i, a in enumerate([*first, *second])
        ]

    def bonus(
        self,
        units: Sequence[KnowledgeUnit],
        masteries: Mapping[str, Mastery],
        previous: Sequence[BuiltActivity],
        start_position: int,
        seed: int,
        count: int = 3,
        average: float | None = None,
    ) -> list[PlannedItem]:
        """Défis en plus pour un enfant rapide : les notions de la séance les mieux réussies, plus
        difficiles, dans des formats qu'il n'a pas encore eus pour elles."""
        rng = random.Random(f"{seed}:bonus")
        seen = {k for a in previous for k in a.knowledge_ids}
        used: dict[str, set[ActivityCode]] = {}
        for activity in previous:
            for k in activity.knowledge_ids:
                used.setdefault(k, set()).add(activity.type)
        candidates = sorted(
            (u for u in units if u.id in seen),
            key=lambda u: (-(masteries[u.id].score if u.id in masteries else 0), -u.item.importance, u.id),
        )
        harder: Prefs = lambda u: ((3, 2), None)  # noqa: E731
        playable = [u for u in candidates if self._options(u, (3, 2), None, used, True, rng)]
        activities = self._sequence(playable[:count], harder, list(previous), used, rng)
        why = reason(Rule.BONUS, average=round(average, 2) if average is not None else None)
        return [PlannedItem(start_position + i, Block.BONUS, a, why) for i, a in enumerate(activities)]

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
        planned = [PlannedItem(i, Block.CORE, a, reason(Rule.ERRORS_SESSION)) for i, a in enumerate(items, 1)]
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
            activities.append(self._fresh(code, unit, difficulty, rng))
        return activities

    def _fresh(
        self, code: ActivityCode, unit: KnowledgeUnit, difficulty: int, rng: random.Random
    ) -> BuiltActivity:
        """L'activité, avec une question pas encore posée aux séances précédentes si la notion en
        a une (autre question du QCM, autre affirmation, autre ordre…)."""
        activity_type = self.registry.get(code)
        first = activity_type.build([unit], difficulty, rng)
        if not self.recent or fingerprint(first) not in self.recent:
            return first
        for attempt in range(FRESH_TRIES):
            other = activity_type.build([unit], difficulty, random.Random(f"{rng.random()}:{attempt}"))
            if fingerprint(other) not in self.recent:
                return other
        return first

    def _has_fresh(self, code: ActivityCode, unit: KnowledgeUnit, difficulty: int) -> bool:
        """Ce format peut encore poser à cette notion une question qu'elle n'a pas eue."""
        if not self.recent:
            return True
        activity_type = self.registry.get(code)
        return any(
            fingerprint(activity_type.build([unit], difficulty, random.Random(f"{unit.id}:{code}:{i}")))
            not in self.recent
            for i in range(FRESH_TRIES)
        )

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
                    if d == difficulty
                    and code not in already
                    and (code in allowed if allowed is not None else code not in ON_REQUEST)
                )
                rng.shuffle(codes)
                if VISUAL_FIRST:
                    codes.sort(key=lambda code: code not in VISUAL)
                result += [(code, difficulty) for code in codes if (code, difficulty) not in result]
        # Les formats dont toutes les questions ont déjà été posées aux séances précédentes passent
        # en dernier, quelle que soit leur difficulté (l'ordre reste sinon celui des préférences).
        result.sort(key=lambda option: not self._has_fresh(option[0], unit, option[1]))
        return result

    def _group(
        self, code: ActivityCode, difficulty: int, candidates: list[KnowledgeUnit]
    ) -> list[KnowledgeUnit]:
        """Le plus grand groupe de notions compatibles pour ce jeu, en suivant l'ordre de priorité."""
        activity = self.registry.get(code)
        usable = [u for u in candidates if activity.accepts(u)]
        best: list[KnowledgeUnit] = []
        for start in range(len(usable)):
            chosen: list[KnowledgeUnit] = []
            for unit in usable[start:] + usable[:start]:
                if len(chosen) < activity.max_units and activity.combinable([*chosen, unit], difficulty):
                    chosen.append(unit)
            if len(chosen) > len(best):
                best = chosen
            if len(best) == activity.max_units:
                break
        return best if activity.can_build(best, difficulty) else []

    def _puzzle(
        self, candidates: list[KnowledgeUnit], rng: random.Random, first: bool
    ) -> BuiltActivity | None:
        options = [
            (code, difficulty, units)
            for code, difficulty in PUZZLES
            if code in self.registry.codes and (units := self._group(code, difficulty, candidates))
        ]
        if not options:
            return None
        if first and options[0][0] in FIRST_PUZZLES:
            code, difficulty, units = options[0]
        else:
            # D'abord un jeu dont les questions n'ont pas été posées aux séances précédentes.
            fresh = [
                o
                for o in options
                if fingerprint(self.registry.get(o[0]).build(o[2], o[1], random.Random(f"{o[0]}")))
                not in self.recent
            ]
            code, difficulty, units = rng.choice(fresh or options)
        return self.registry.get(code).build(units, difficulty, rng)

    def _speed(self, candidates: list[KnowledgeUnit], rng: random.Random) -> BuiltActivity | None:
        speed = self.registry.get(ActivityCode.SPEED_CHALLENGE)
        chosen = [u for u in candidates if speed.accepts(u)][:SPEED_NOTIONS]
        if not chosen or not speed.can_build(chosen, 1):
            return None
        activity = speed.build(chosen, 1, rng)
        for attempt in range(FRESH_TRIES if fingerprint(activity) in self.recent else 0):
            other = speed.build(chosen, 1, random.Random(f"speed:{attempt}:{rng.random()}"))
            if fingerprint(other) not in self.recent:
                return other
        return activity

    def estimate_duration_s(self, activities: Sequence[BuiltActivity], with_replay: bool) -> int:
        """§8.2 : durées de base + transitions + corrections (+ provision pour la reprise)."""
        seconds = sum(
            self.registry.get(a.type).base_duration_s + TRANSITION_S + CORRECTION_S for a in activities
        )
        return math.ceil(seconds + (REPLAY_PROVISION_S if with_replay else 0))


_QUESTION_KEYS = (
    "statement",
    "text",
    "front",
    "word",
    "words",
    "letters",
    "items",
    "statements",  # défi rapide
    "left",  # association
    "clues",  # trouver la correspondance
    "spins",  # roue aléatoire
    "boxes",  # ouvrir la boîte
    "cards",  # memory, cartes aléatoires
    "prompt",
)


def fingerprint(activity: BuiltActivity) -> str:
    """Ce que l'enfant voit de la question, pour reconnaître une question déjà posée d'une séance à
    l'autre : le type et le premier texte qui la distingue (énoncé, phrase, carte, mot…). Les
    étiquettes à remettre dans l'ordre sont triées : leur mélange ne fait pas une autre question."""
    payload = activity.payload
    for key in _QUESTION_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            texts = sorted(
                str(v.get("text") or v.get("prompt") or v.get("front") or "")
                if isinstance(v, dict)
                else str(v)
                for v in value
            )
            return f"{activity.type}:{key}:{normalize(' '.join(texts))}"
        if isinstance(value, str) and value:
            return f"{activity.type}:{key}:{normalize(value)}"
    return f"{activity.type}:{normalize(str(sorted(payload)))}"


def _visual(activity: BuiltActivity, why: Reason) -> Reason:
    """Un jeu visuel choisi avant les autres formats le dit (règle `visual_first`, étape 25)."""
    if VISUAL_FIRST and activity.type in VISUAL:
        why["facts"]["visual_first"] = True
    return why


def _eligible(units: Sequence[KnowledgeUnit]) -> list[KnowledgeUnit]:
    """Les notions d'importance ≤ 2 ne servent que si la leçon a moins de 6 notions importantes."""
    strong = [u for u in units if u.item.importance >= IMPORTANT]
    return strong if len(strong) >= STRONG_NOTIONS_NEEDED else list(units)


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
