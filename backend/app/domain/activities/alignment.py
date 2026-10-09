"""« Points alignés » (ALIGN) : les exercices d'alignement d'une fiche de géométrie, refaits sur
le téléphone avec une figure dessinée par le code (`app.domain.geometry`).

- difficulté 1 : « Les 3 points sont-ils alignés ? » → oui / non ;
- difficulté 2 : « Touche les 4 points (ou clous) alignés » parmi 7 ;
- difficulté 3 : « Touche les points alignés avec les 2 points bleus » parmi 10.

Proposé pour une notion de maths qui parle d'alignement. La figure change à chaque fois (une
nouvelle graine) ; la réponse est calculée, jamais devinée. Les points sont nommés A, B, C… pour
que la correction dise lesquels étaient alignés.
"""

import random
import re
from typing import Any

from pydantic import Field

from app.domain import geometry
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
from app.domain.knowledge import KnowledgeUnit, Subject, Theme
from app.domain.text import normalize

_TOPIC = re.compile(r"\balign")
YES_NO = [{"id": "oui", "text": "Oui"}, {"id": "non", "text": "Non"}]


class AlignChoice(ResponseModel):
    choice_id: str


class AlignSelection(ResponseModel):
    selected: list[str] = Field(max_length=len(geometry.LETTERS))


def is_alignment(unit: KnowledgeUnit) -> bool:
    """Leçon de maths sur les alignements : thème choisi par l'IA (§5.47) ou mots de la notion."""
    if unit.subject != Subject.MATH:
        return False
    return unit.item.theme == Theme.ALIGNMENT or bool(_TOPIC.search(normalize(unit.item.corpus())))


class Alignment(ActivityType):
    code = ActivityCode.ALIGN
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return is_alignment(unit)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        figure_rng = random.Random(rng.random())
        if difficulty == 1:
            aligned = rng.random() < 0.5
            figure = geometry.three_points(figure_rng, aligned)
            a, b, c = (p.id for p in figure.points)
            question: dict[str, Any] = {
                "prompt": "Les 3 points sont-ils alignés ?",
                "task": "yes_no",
                "points": [p.to_json() for p in figure.points],
                "choices": YES_NO,
            }
            display = (
                f"Oui, {a}, {b} et {c} sont sur une même droite."
                if aligned
                else f"Non, {b} n'est pas sur la droite qui passe par {a} et {c}."
            )
            return question, {"choice_id": "oui" if aligned else "non", "display": display, **feedback(unit)}
        if difficulty == 2:
            figure = geometry.aligned_among(figure_rng, 4, 7)
            thing = rng.choice(("points", "clous"))
            prompt = f"Touche les 4 {thing} alignés."
            display = f"Les points {geometry.listed(figure.answer)} sont alignés."
            shape = "nail" if thing == "clous" else "dot"
        else:
            figure = geometry.aligned_with_blue(figure_rng, 10)
            blue = [p.id for p in figure.points if p.color == "blue"]
            prompt = "Touche les points alignés avec les 2 points bleus."
            display = (
                f"Les points {geometry.listed(figure.answer)} sont sur la droite qui passe par "
                f"{blue[0]} et {blue[1]}."
            )
            shape = "dot"
        payload: dict[str, Any] = {
            "prompt": prompt,
            "task": "select",
            "shape": shape,
            "points": [p.to_json() for p in figure.points],
        }
        if difficulty == 2:
            payload["count"] = 4
        return payload, {"expected": sorted(figure.answer), "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        solution, knowledge_id = activity.solution, activity.knowledge_ids[0]
        if activity.payload["task"] == "yes_no":
            choice = parse_response(AlignChoice, response).choice_id
            if choice not in ("oui", "non"):
                raise InvalidResponse(f"choix inconnu : {choice}")
            score = 1.0 if choice == solution["choice_id"] else 0.0
        else:
            selected = set(parse_response(AlignSelection, response).selected)
            names = {p["id"] for p in activity.payload["points"]}
            if not selected <= names:
                raise InvalidResponse("point inconnu")
            expected = set(solution["expected"])
            # Un point oublié ou un point de trop compte ; tout juste seulement si c'est exact.
            found = len(selected & expected) - len(selected - expected)
            score = 1.0 if selected == expected else max(0.0, round(found / len(expected), 2) - 0.25)
        return Grade(
            score=score,
            evidence={knowledge_id: score},
            errors={} if score == 1 else {knowledge_id: ErrorType.METHOD},
            correct_answer=solution["display"],
            tip=solution.get("tip"),
            explanation=solution.get("explanation"),
        )
