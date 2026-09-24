"""Activités sur une figure (étape 22) : situer sur une carte ou un schéma, et colorier.

- Carte (`MAP`) : « Touche la Bretagne », puis la Normandie… sur la même figure ; chaque notion
  dont le nom est une zone de la figure est une question.
- Coloriage (`COLORING`) : une notion de classification dont les éléments sont des zones d'une
  même figure (« Planètes telluriques : Mercure, Vénus… ; planètes gazeuses : Jupiter… ») ;
  chaque catégorie a sa couleur, l'enfant colorie les zones. Les zones à colorier ne sont pas
  montrées : il faut savoir où elles sont et dans quelle catégorie elles vont.
"""

import random
from typing import Annotated, Any

from pydantic import Field, StringConstraints

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
from app.domain.figures import Figure, FigureLibrary, Zone, default_library
from app.domain.knowledge import ClassificationAttributes, KnowledgeType, KnowledgeUnit

ZoneId = Annotated[str, StringConstraints(min_length=1, max_length=60)]
MAX_ZONES = 120  # départements de France compris
PALETTE = (("rouge", "#e5484d"), ("bleu", "#3d7cc9"), ("vert", "#2eb872"), ("jaune", "#f5c518"))
MIN_COLORED = 3
MAX_COLORED = 12


def _members(texts: dict[str, str], expected: dict[str, str], palette_id: str) -> list[str]:
    return [text for zone, text in texts.items() if expected[zone] == palette_id]


class MapResponse(ResponseModel):
    answers: list[tuple[str, ZoneId]] = Field(min_length=1, max_length=5)  # (question, zone touchée)


class ColoringResponse(ResponseModel):
    colors: list[tuple[ZoneId, str]] = Field(max_length=MAX_ZONES)  # (zone, couleur)


class _OnFigure(ActivityType):
    def __init__(self, library: FigureLibrary | None = None) -> None:
        self.library = library or default_library()

    def _figure(self, activity: BuiltActivity) -> Figure | None:
        return self.library.get(activity.payload["figure"]["id"])


class MapLocate(_OnFigure):
    code = ActivityCode.MAP
    knowledge_types = ALL_TYPES - {KnowledgeType.FORMULA, KnowledgeType.RULE}
    difficulties = frozenset({2})
    base_duration_s = 60
    multi_knowledge = True
    min_units = 2
    max_units = 5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return self.library.matches(unit.item.label)

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return self.library.placement([u.item.label for u in units]) is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        placement = self.library.placement([u.item.label for u in units])
        assert placement is not None
        figure, zones = placement
        pairs = list(zip(units, zones, strict=True))
        rng.shuffle(pairs)
        items = [{"id": f"q{i}", "text": zone.name} for i, (_, zone) in enumerate(pairs, start=1)]
        payload = {
            "prompt": f"{figure.title} : touche sur le dessin chaque nom demandé.",
            "figure": figure.ref,
            "items": items,
        }
        solution = {
            "zones": {item["id"]: zone.id for item, (_, zone) in zip(items, pairs, strict=True)},
            "knowledge_by_item": {item["id"]: unit.id for item, (unit, _) in zip(items, pairs, strict=True)},
            "display": "Regarde où se trouve chaque nom sur le dessin.",
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        answers = parse_response(MapResponse, response).answers
        expected: dict[str, str] = activity.solution["zones"]
        questions = [q for q, _ in answers]
        if len(set(questions)) != len(questions) or set(questions) != set(expected):
            raise InvalidResponse("il faut répondre à chaque question une fois")
        figure = self._figure(activity)
        touched = dict(answers)
        details: list[dict[str, Any]] = []
        for question, zone_id in expected.items():
            given = figure.zone(touched[question]) if figure else None
            details.append(
                {
                    "id": question,
                    "correct": touched[question] == zone_id,
                    "zone": zone_id,
                    "touched": touched[question],
                    "touched_name": given.name if given else None,
                }
            )
        knowledge_by_item: dict[str, str] = activity.solution["knowledge_by_item"]
        evidence = {knowledge_by_item[d["id"]]: 1.0 if d["correct"] else 0.0 for d in details}
        return Grade(
            score=sum(evidence.values()) / len(evidence),
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, v in evidence.items() if v < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )


class Coloring(_OnFigure):
    code = ActivityCode.COLORING
    knowledge_types = frozenset({KnowledgeType.CLASSIFICATION})
    difficulties = frozenset({2})
    base_duration_s = 75

    def _plan(self, unit: KnowledgeUnit) -> tuple[Figure, list[tuple[str, list[tuple[str, Zone]]]]] | None:
        """La figure, et pour chaque catégorie ses éléments avec leur zone."""
        categories = ClassificationAttributes.model_validate(unit.item.attributes).categories
        members = [m for c in categories for m in c.members]
        if not 2 <= len(categories) <= len(PALETTE) or not MIN_COLORED <= len(members) <= MAX_COLORED:
            return None
        placement = self.library.placement(members)
        if placement is None:
            return None
        figure, zones = placement
        by_member = iter(zones)
        return figure, [(c.name, [(m, next(by_member)) for m in c.members]) for c in categories]

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return self._plan(unit) is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        plan = self._plan(unit)
        assert plan is not None
        figure, categories = plan
        palette, expected, texts, names = [], {}, {}, {}
        for index, ((category, members), (colour_name, colour)) in enumerate(
            zip(categories, PALETTE, strict=False), start=1
        ):
            palette_id = f"p{index}"
            palette.append({"id": palette_id, "name": category, "color": colour, "color_name": colour_name})
            names[palette_id] = category
            for member, zone in members:
                expected[zone.id] = palette_id
                texts[zone.id] = member
        payload = {
            "prompt": f"Colorie le dessin selon la légende : {unit.item.label}",
            "figure": figure.ref,
            "palette": palette,
            "count": len(expected),
        }
        solution = {
            "expected": expected,
            "names": names,
            "texts": texts,
            "display": " ; ".join(
                f"{p['color_name']} : {p['name']} ({', '.join(_members(texts, expected, p['id']))})"
                for p in palette
            ),
            **feedback(unit),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        colors = parse_response(ColoringResponse, response).colors
        zones = [zone for zone, _ in colors]
        if len(set(zones)) != len(zones):
            raise InvalidResponse("une zone coloriée deux fois")
        names: dict[str, str] = activity.solution["names"]
        if not {c for _, c in colors} <= set(names):
            raise InvalidResponse("couleur inconnue")
        expected: dict[str, str] = activity.solution["expected"]
        colours = {p["id"]: p["color"] for p in activity.payload["palette"]}
        given = dict(colors)
        details = [
            {
                "id": zone,
                "text": activity.solution["texts"][zone],
                "correct": given.get(zone) == palette_id,
                "expected": names[palette_id],
                "zone": zone,
                "color": colours[palette_id],
            }
            for zone, palette_id in expected.items()
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
