"""Remettre dans l'ordre (étape 21) : les étapes d'un processus (ORDER) et les événements d'une
leçon sur une frise chronologique (TIMELINE). L'enfant déplace les étiquettes ; chaque étiquette
à sa place compte."""

import random
import re
from typing import Any

from pydantic import Field

from app.domain.activities.base import (
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.errors import ErrorType
from app.domain.knowledge import (
    DateAttributes,
    EventAttributes,
    KnowledgeType,
    KnowledgeUnit,
    ProcessAttributes,
)
from app.domain.text import normalize

MIN_STEPS = 3
MAX_STEPS = 8

MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}  # fmt: skip
_YEAR = re.compile(r"(-?\d{1,4})(?!\d)")
_DAY = re.compile(r"\b(\d{1,2})(?:er)?\s+([a-z]+)\b")


class OrderResponse(ResponseModel):
    order: list[str] = Field(max_length=MAX_STEPS)


def date_key(value: str) -> tuple[int, int, int] | None:
    """« 14 juillet 1789 » → (1789, 7, 14) ; « 52 av. J.-C. » → (-52, 0, 0) ; illisible → None."""
    text = normalize(value)
    years = _YEAR.findall(text)
    if not years:
        return None
    year = int(years[-1])
    if re.search(r"\bav(ant)?\b|\bav\.?\s*j", text) and year > 0:
        year = -year
    month = day = 0
    if (found := _DAY.search(text)) and found.group(2) in MONTHS:
        day, month = int(found.group(1)), MONTHS[found.group(2)]
    elif found_month := next((m for name, m in MONTHS.items() if re.search(rf"\b{name}\b", text)), None):
        month = found_month
    return year, month, day


def comparable(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    """Deux dates s'ordonnent sans discussion : années différentes, ou même précision."""
    if a[0] != b[0]:
        return True
    if (a[1] == 0) != (b[1] == 0):
        return False
    return a[1] != b[1] or (a[2] == 0) == (b[2] == 0)


def _shuffled(ids: list[str], rng: random.Random) -> list[str]:
    """Mélange qui ne laisse jamais la bonne réponse telle quelle."""
    order = list(ids)
    while order == ids:
        rng.shuffle(order)
    return order


def grade_order(activity: BuiltActivity, response: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    given = parse_response(OrderResponse, response).order
    expected: list[str] = activity.solution["order"]
    if sorted(given) != sorted(expected):
        raise InvalidResponse("il faut placer chaque étiquette une fois")
    texts: dict[str, str] = activity.solution["texts"]
    details = [
        {
            "id": item_id,
            "correct": given[position] == item_id,
            "expected": texts[item_id],
            "position": position + 1,
        }
        for position, item_id in enumerate(expected)
    ]
    return details, sum(1 for d in details if d["correct"]) / len(expected)


class Order(ActivityType):
    """Remets dans l'ordre les étapes d'un processus (« Les étapes de la digestion »)."""

    code = ActivityCode.ORDER
    knowledge_types = frozenset({KnowledgeType.PROCESS})
    difficulties = frozenset({2})
    base_duration_s = 45

    def _steps(self, unit: KnowledgeUnit) -> list[str]:
        steps = ProcessAttributes.model_validate(unit.item.attributes).steps
        return steps[:MAX_STEPS]

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        steps = self._steps(unit)
        return len(steps) >= MIN_STEPS and len({normalize(s) for s in steps}) == len(steps)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        steps = self._steps(unit)
        ids = [f"s{i}" for i in range(1, len(steps) + 1)]
        texts = dict(zip(ids, steps, strict=True))
        payload = {
            "prompt": f"Remets dans l'ordre : {unit.item.label}",
            "items": [{"id": i, "text": texts[i]} for i in _shuffled(ids, rng)],
        }
        solution = {
            "order": ids,
            "texts": texts,
            "display": " → ".join(steps),
            **feedback(unit),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        details, score = grade_order(activity, response)
        knowledge = activity.knowledge_ids[0]
        return Grade(
            score=score,
            evidence={knowledge: score},
            errors={knowledge: ErrorType.METHOD} if score < 1 else {},
            correct_answer=activity.solution["display"],
            tip=activity.solution.get("tip"),
            explanation=activity.solution.get("explanation"),
            details=details,
        )


def dated(unit: KnowledgeUnit) -> tuple[str, str] | None:
    """(date, événement) d'une notion datée : une date (« 1789 », la prise de la Bastille) ou un
    événement dont la date est connue."""
    if unit.type is KnowledgeType.DATE:
        date = DateAttributes.model_validate(unit.item.attributes)
        return date.value, date.event
    if unit.type is KnowledgeType.EVENT:
        event = EventAttributes.model_validate(unit.item.attributes)
        return (event.date, unit.item.label) if event.date else None
    return None


class Timeline(ActivityType):
    """Frise chronologique : place les événements de la leçon du plus ancien au plus récent."""

    code = ActivityCode.TIMELINE
    knowledge_types = frozenset({KnowledgeType.DATE, KnowledgeType.EVENT})
    difficulties = frozenset({2})
    base_duration_s = 60
    multi_knowledge = True
    min_units = 3
    max_units = 5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        found = dated(unit)
        return found is not None and date_key(found[0]) is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        keys = [self._key(u) for u in units]
        events = {normalize(self._dated(u)[1]) for u in units}
        # Pas deux événements à la même date, ni une année seule (« 1789 ») face à un jour de
        # cette année (« 5 mai 1789 ») : l'ordre serait discutable.
        return len(set(keys)) == len(keys) == len(events) and all(
            comparable(a, b) for i, a in enumerate(keys) for b in keys[i + 1 :]
        )

    def _dated(self, unit: KnowledgeUnit) -> tuple[str, str]:
        found = dated(unit)
        assert found is not None
        return found

    def _key(self, unit: KnowledgeUnit) -> tuple[int, int, int]:
        key = date_key(self._dated(unit)[0])
        assert key is not None
        return key

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        chronological = sorted(units, key=self._key)
        ids = [f"e{i}" for i in range(1, len(units) + 1)]
        texts, events, knowledge_by_item = {}, {}, {}
        for item_id, unit in zip(ids, chronological, strict=True):
            date, event = self._dated(unit)
            texts[item_id] = f"{date} : {event}"
            events[item_id] = event
            knowledge_by_item[item_id] = unit.id
        payload = {
            "prompt": "Place les événements sur la frise, du plus ancien au plus récent.",
            "items": [{"id": i, "text": events[i]} for i in _shuffled(ids, rng)],
        }
        solution = {
            "order": ids,
            "texts": texts,
            "knowledge_by_item": knowledge_by_item,
            "display": " → ".join(texts[i] for i in ids),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        details, score = grade_order(activity, response)
        knowledge_by_item: dict[str, str] = activity.solution["knowledge_by_item"]
        evidence = {knowledge_by_item[d["id"]]: 1.0 if d["correct"] else 0.0 for d in details}
        return Grade(
            score=score,
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, result in evidence.items() if result < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )
