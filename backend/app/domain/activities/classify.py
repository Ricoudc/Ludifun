"""Ranger dans les bonnes cases (étape 21) : chaque élément dans sa catégorie (« Mammifères /
Oiseaux / Poissons »), à partir d'une notion de classification, ou du jeu de tri que l'IA a
proposé pour une autre notion (« Nom ou verbe ? », étape 25)."""

import random
from typing import Any

from pydantic import Field

from app.domain.activities.base import (
    ALL_TYPES,
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
from app.domain.knowledge import ClassificationAttributes, KnowledgeType, KnowledgeUnit
from app.domain.text import normalize

MAX_CATEGORIES = 4
MAX_ITEMS = 10
MIN_ITEMS = 3


class ClassifyResponse(ResponseModel):
    assignments: list[tuple[str, str]] = Field(max_length=MAX_ITEMS)  # (élément, catégorie)


class Classify(ActivityType):
    code = ActivityCode.CLASSIFY
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 60

    def _categories(self, unit: KnowledgeUnit) -> list[tuple[str, list[str]]]:
        """Catégories et éléments retenus : 2 à 4 catégories, 10 éléments au plus, répartis."""
        found: list[tuple[str, list[str]]] = []
        if unit.type == KnowledgeType.CLASSIFICATION:
            attributes = ClassificationAttributes.model_validate(unit.item.attributes)
            found = [(c.name, c.members) for c in attributes.categories[:MAX_CATEGORIES]]
        elif unit.material.sorting is not None:
            found = [(c.name, c.members) for c in unit.material.sorting.categories[:MAX_CATEGORIES]]
        if not found:
            return []
        per_category = max(1, MAX_ITEMS // len(found))
        return [(name, members[:per_category]) for name, members in found]

    def _prompt(self, unit: KnowledgeUnit) -> str:
        if unit.type != KnowledgeType.CLASSIFICATION and unit.material.sorting is not None:
            return unit.material.sorting.prompt
        return f"Range chaque étiquette dans la bonne case : {unit.item.label}"

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        categories = self._categories(unit)
        members = [normalize(m) for _, items in categories for m in items]
        names = {normalize(name) for name, _ in categories}
        # Un élément dans deux catégories rendrait le rangement ambigu.
        return (
            len(categories) >= 2
            and len(members) >= MIN_ITEMS
            and len(set(members)) == len(members)
            and (len(names) == len(categories))
        )

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        categories: list[dict[str, str]] = []
        items: list[dict[str, str]] = []
        expected: dict[str, str] = {}
        texts: dict[str, str] = {}
        for c_index, (name, members) in enumerate(self._categories(unit), start=1):
            category_id = f"c{c_index}"
            categories.append({"id": category_id, "name": name})
            for member in members:
                item_id = f"i{len(items) + 1}"
                items.append({"id": item_id, "text": member})
                expected[item_id] = category_id
                texts[item_id] = member
        rng.shuffle(items)
        names = {c["id"]: c["name"] for c in categories}
        payload = {
            "prompt": self._prompt(unit),
            "categories": categories,
            "items": items,
        }
        solution = {
            "categories": expected,
            "names": names,
            "texts": texts,
            "display": " ; ".join(
                f"{c['name']} : {', '.join(texts[i] for i, cat in expected.items() if cat == c['id'])}"
                for c in categories
            ),
            **feedback(unit),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(ClassifyResponse, response).assignments
        expected: dict[str, str] = activity.solution["categories"]
        names: dict[str, str] = activity.solution["names"]
        items = [item for item, _ in given]
        if len(set(items)) != len(items) or set(items) != set(expected):
            raise InvalidResponse("il faut ranger chaque élément une fois")
        if not {category for _, category in given} <= set(names):
            raise InvalidResponse("case inconnue")
        answers = dict(given)
        details = [
            {"id": item, "correct": answers[item] == category, "expected": names[category]}
            for item, category in expected.items()
        ]
        score = sum(1 for d in details if d["correct"]) / len(details)
        knowledge = activity.knowledge_ids[0]
        return Grade(
            score=score,
            evidence={knowledge: score},
            errors={knowledge: ErrorType.CONFUSION} if score < 1 else {},
            correct_answer=activity.solution["display"],
            tip=activity.solution.get("tip"),
            explanation=activity.solution.get("explanation"),
            details=details,
        )
