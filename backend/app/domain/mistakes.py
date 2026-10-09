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
    ActivityCode.FIND_MATCH: "Trouver la correspondance",
    ActivityCode.RANDOM_CARDS: "Cartes aléatoires",
    ActivityCode.PICTURE_MATCH: "Image et mot",
    ActivityCode.PICTURE_FIND: "Quelle image ?",
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
        case ActivityCode.NUMBER_LINE | ActivityCode.FRACTION_BAR if "choices" in payload:
            given = _texts(payload.get("choices")).get(response.get("choice_id", ""), "?")
        case ActivityCode.NUMBER_LINE:
            given = f"Graduation n° {response.get('index', '?')}"
        case ActivityCode.FRACTION_BAR:
            given = f"{len(response.get('colored', []))} part(s) coloriée(s) sur {payload.get('parts', '?')}"
        case ActivityCode.WORD_HUNT:
            words = _texts(payload.get("words"))
            touched = [words.get(str(w), "?") for w in response.get("selected", [])]
            given = "Mots touchés : " + (", ".join(touched) if touched else "aucun")
        case ActivityCode.CONJUGATION | ActivityCode.HOMOPHONE:
            rows, chips = _texts(payload.get("items")), _texts(payload.get("choices"))
            chosen = dict(response.get("answers", []))
            picked = {row: chips.get(choice, choice) for row, choice in chosen.items()}
            given = _lines([f"{rows.get(d['id'], '?')} → {picked.get(d['id'], 'rien')}" for d in wrong])
            expected = _lines([d["expected"] for d in wrong])
        case ActivityCode.COLUMN_OP:
            given = str(response.get("result", "")).strip() or "(rien écrit)"
        case ActivityCode.ALIGN if payload.get("task") == "yes_no":
            given = _texts(payload.get("choices")).get(response.get("choice_id", ""), "?")
        case ActivityCode.ALIGN:
            touched = sorted(str(p) for p in response.get("selected", []))
            given = "Points touchés : " + (", ".join(touched) if touched else "aucun")
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
        case ActivityCode.RULER:
            given = _texts(payload.get("choices")).get(response.get("choice_id", ""), "?")
        case ActivityCode.SYMMETRY:
            cells = {tuple(c) for c in response.get("selected", [])}
            right = len(cells & {tuple(c) for c in activity.solution.get("expected", [])})
            given = f"{len(cells)} case(s) coloriée(s), dont {right} juste(s)"
            if cells == {tuple(c) for c in activity.solution.get("slid", [])}:
                given += " : la figure a glissé au lieu d'être retournée"
        case ActivityCode.SYLLABLES:
            given = _lines([d["given"] or "(pas coupé)" for d in wrong])
            expected = _lines([d["expected"] for d in wrong])
        case ActivityCode.CLOCK | ActivityCode.MONEY if "choices" in payload:
            given = _texts(payload.get("choices")).get(response.get("choice_id", ""), "?")
        case ActivityCode.MONEY:
            values = {i["id"]: i["value"] for i in payload.get("items", []) if isinstance(i, dict)}
            paid = sum(values.get(str(i), 0) for i in response.get("selected", []))
            given = f"A payé {paid // 100},{paid % 100:02d} €" if paid % 100 else f"A payé {paid // 100} €"
        case ActivityCode.ORDER | ActivityCode.TIMELINE | ActivityCode.ALPHA_ORDER:
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
        case ActivityCode.UNJUMBLE:
            words = _texts(payload.get("words"))
            question = "Démêler : " + " / ".join(words.values())
            given = " ".join(words.get(i, "?") for i in response.get("order", [])) or "(rien placé)"
        case ActivityCode.FIND_MATCH:
            clues, targets = _texts(payload.get("clues")), _texts(payload.get("targets"))
            chosen = dict(response.get("answers", []))
            given = _lines(
                [
                    f"{clues.get(d['id'], '?')} → {targets.get(chosen.get(d['id'], ''), 'pas de réponse')}"
                    for d in wrong
                ]
            )
            expected = _lines([f"{clues.get(d['id'], '?')} → {d['expected']}" for d in wrong])
        case ActivityCode.PICTURE_MATCH:
            # Le parent ne voit pas les images ici : seulement le mot choisi pour chacune.
            words = _texts(payload.get("words"))
            chosen = dict(response.get("pairs", []))
            question = "Image et mot : relier chaque image à son mot"
            given = _lines(
                [f"{d['text']} → {words.get(chosen.get(d['id'], ''), 'pas reliée')}" for d in wrong]
            )
            expected = _lines([f"{d['text']} → {d['expected']}" for d in wrong])
        case ActivityCode.PICTURE_FIND:
            question = "Quelle image ? : toucher l'image qui montre chaque phrase"
            given = _lines([f"« {d['text']} » : mauvaise image" for d in wrong])
            expected = _lines([f"« {d['text']} » : {d['expected']}" for d in wrong])
        case ActivityCode.WHEEL | ActivityCode.BOX:
            questions = {
                q["id"]: q for q in payload.get("spins") or payload.get("boxes") or [] if isinstance(q, dict)
            }
            question = "Roue aléatoire" if code is ActivityCode.WHEEL else "Ouvrir la boîte"
            answers = {a["id"]: a["choice_id"] for a in response.get("answers", [])}
            given = _lines(
                [
                    f"{questions.get(d['id'], {}).get('prompt', '?')} : "
                    + _texts(questions.get(d["id"], {}).get("choices")).get(
                        answers.get(d["id"], ""), "pas de réponse"
                    )
                    for d in wrong
                ]
            )
            expected = _lines(
                [f"{questions.get(d['id'], {}).get('prompt', '?')} : {d['expected']}" for d in wrong]
            )
        case ActivityCode.RANDOM_CARDS:
            fronts = {c["id"]: c["front"] for c in payload.get("cards", []) if isinstance(c, dict)}
            given = _lines([f"{fronts.get(d['id'], '?')} : « Je ne savais pas »" for d in wrong])
            expected = _lines([f"{fronts.get(d['id'], '?')} : {d['expected']}" for d in wrong])
        case _:
            return None
    return Mistake(question=question, given=given, expected=expected)


def question_of(activity: BuiltActivity) -> str:
    """La question telle que l'enfant l'a vue, sans sa réponse (aides demandées, §16)."""
    payload, code = activity.payload, activity.type
    match code:
        case ActivityCode.FILL_BLANK:
            return str(payload.get("text", ""))
        case ActivityCode.WORD_FLASH:
            return f"Mot éclair : écrire « {payload.get('word', '?')} » de mémoire"
        case ActivityCode.DICTATION:
            return "Dictée : écrire le mot entendu à voix haute"
        case ActivityCode.SCRAMBLE:
            return "Lettres mélangées : " + " ".join(_texts(payload.get("letters")).values())
        case ActivityCode.FLASHCARD:
            return str(payload.get("front", ""))
        case ActivityCode.UNJUMBLE:
            return "Démêler : " + " / ".join(_texts(payload.get("words")).values())
    return str(payload.get("prompt") or payload.get("statement") or QUESTION_OF.get(code, code.value))
