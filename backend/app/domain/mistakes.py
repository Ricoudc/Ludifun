"""Erreurs aux questions, lisibles par le parent : la question, ce que l'enfant a répondu, la bonne
réponse.

Tout se déduit de l'activité enregistrée (charge utile, solution) et de la réponse de l'enfant, en
recorrigeant avec le code de l'activité : rien n'est demandé à l'IA. Pour les jeux à plusieurs
éléments (relier, ranger, frise…), seuls les éléments ratés sont décrits.
"""

from dataclasses import dataclass
from typing import Any

from app.domain.activities.base import ActivityCode, BuiltActivity, InvalidResponse
from app.domain.activities.registry import ActivityRegistry, UnknownActivity

MAX_LINES = 5  # éléments ratés montrés par jeu

QUESTION_OF: dict[ActivityCode, str] = {
    ActivityCode.MATCH: "Relier chaque élément à sa réponse",
    ActivityCode.SPEED_CHALLENGE: "Défi rapide : vrai ou faux ?",
    ActivityCode.MEMORY: "Memory : retrouver les paires",
}


@dataclass(frozen=True)
class Mistake:
    question: str
    given: str  # la réponse de l'enfant
    expected: str  # la bonne réponse


def _texts(items: Any) -> dict[str, str]:
    return {i["id"]: i["text"] for i in items or [] if isinstance(i, dict) and "id" in i and "text" in i}


def _yes_no(value: object) -> str:
    return "Vrai" if value else "Faux"


def _lines(lines: list[str]) -> str:
    more = len(lines) - MAX_LINES
    return "\n".join(lines[:MAX_LINES] + ([f"… et {more} autre(s)"] if more > 0 else []))


def describe(registry: ActivityRegistry, activity: BuiltActivity, response: dict[str, Any]) -> Mistake | None:
    """None si la réponse ne se relit pas (type inconnu, format d'une ancienne version)."""
    try:
        grade = registry.for_activity(activity).grade(activity, response)
    except (UnknownActivity, InvalidResponse, KeyError, TypeError, ValueError):
        return None
    payload, code = activity.payload, activity.type
    question = str(payload.get("prompt") or payload.get("statement") or QUESTION_OF.get(code, ""))
    wrong = [d for d in grade.details if d.get("correct") is False]
    given: str
    expected = grade.correct_answer
    match code:
        case ActivityCode.MCQ:
            given = _texts(payload.get("choices")).get(response.get("choice_id", ""), "?")
        case ActivityCode.TRUE_FALSE:
            given = _yes_no(response.get("value"))
        case ActivityCode.FILL_BLANK:
            question = str(payload.get("text", ""))
            given = str(response.get("text", "")).strip() or "(rien écrit)"
        case ActivityCode.OPEN_QUESTION:
            given = str(response.get("text", "")).strip() or "(rien écrit)"
        case ActivityCode.WORD_FLASH:
            question = f"Mot éclair : écrire « {payload.get('word', '?')} » de mémoire"
            given = str(response.get("text", "")).strip() or "(rien écrit)"
        case ActivityCode.DICTATION:
            question = f"Dictée : écrire « {payload.get('word', '?')} » entendu à voix haute"
            given = str(response.get("text", "")).strip() or "(rien écrit)"
        case ActivityCode.SCRAMBLE:
            letters = _texts(payload.get("letters"))
            question = "Lettres mélangées : " + " ".join(letters.values())
            given = "".join(letters.get(i, "?") for i in response.get("order", [])) or "(rien placé)"
        case ActivityCode.FLASHCARD:
            question = str(payload.get("front", ""))
            given = "« Je ne savais pas »"
            expected = str(payload.get("back", expected))
        case ActivityCode.MATCH:
            lefts, rights = _texts(payload.get("left")), _texts(payload.get("right"))
            chosen = dict(response.get("pairs", []))
            given = _lines(
                [
                    f"{lefts.get(d['id'], '?')} → {rights.get(chosen.get(d['id'], ''), 'pas relié')}"
                    for d in wrong
                ]
            )
            expected = _lines([f"{lefts.get(d['id'], '?')} → {d['expected']}" for d in wrong])
        case ActivityCode.SPEED_CHALLENGE:
            statements = _texts(payload.get("statements"))
            answers = {a["id"]: a["value"] for a in response.get("answers", [])}
            given = _lines(
                [
                    f"« {statements.get(d['id'], '?')} » : "
                    + (_yes_no(answers[d["id"]]) if d["id"] in answers else "pas de réponse")
                    for d in wrong
                ]
            )
            expected = _lines(
                [
                    f"« {statements.get(d['id'], '?')} » : {_yes_no(d['expected'])}"
                    + (f" ({d['correction']})" if d.get("correction") else "")
                    for d in wrong
                ]
            )
        case ActivityCode.ORDER | ActivityCode.TIMELINE:
            items = _texts(payload.get("items"))
            given = " → ".join(items.get(i, "?") for i in response.get("order", []))
        case ActivityCode.CLASSIFY:
            items = _texts(payload.get("items"))
            boxes = {c["id"]: c["name"] for c in payload.get("categories", [])}
            placed = dict(response.get("assignments", []))
            given = _lines(
                [
                    f"{items.get(d['id'], '?')} → {boxes.get(placed.get(d['id'], ''), 'pas rangé')}"
                    for d in wrong
                ]
            )
            expected = _lines([f"{items.get(d['id'], '?')} → {d['expected']}" for d in wrong])
        case ActivityCode.MAP:
            items = _texts(payload.get("items"))
            given = _lines(
                [f"{items.get(d['id'], '?')} : touché « {d.get('touched_name') or '?'} »" for d in wrong]
            )
            expected = "Regarde sur le dessin où se trouve chaque nom."
        case ActivityCode.COLORING:
            given = f"{len(wrong)} zone(s) mal coloriée(s)"
            expected = _lines([f"{d.get('text', '?')} : {d['expected']}" for d in wrong])
        case ActivityCode.MEMORY:
            given = f"{len(response.get('moves', []))} cartes retournées"
        case _:
            return None
    return Mistake(question=question, given=given, expected=expected)
