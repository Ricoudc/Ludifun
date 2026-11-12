"""Le parent corrige lui-même une question de la leçon (spécification technique §5.59).

L'IA peut se tromper (« Quel pronom va avec "Nous ___ contents" ? » réponse retenue : avons). Le
parent voit la question, sa bonne réponse et les mauvaises, et les corrige : énoncé, réponse,
mauvaises réponses d'un QCM ; une affirmation et si elle est vraie ou fausse ; un texte à trous
et ses réponses acceptées ; une association ; une carte mémoire. Rien n'est demandé à l'IA.

Le matériel corrigé repasse par son schéma (`KnowledgeMaterial`) : trois mauvaises réponses
différentes de la bonne, un seul « ___ » dans un texte à trous… La progression de l'enfant
n'est jamais touchée : seules les prochaines activités changent.

Domaine pur : pas de base, pas de réseau.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.knowledge import KnowledgeMaterial
from app.domain.text import normalize

Kind = Literal["question", "statement", "cloze", "pair", "flashcard"]


class EditError(ValueError):
    """La correction ne peut pas être appliquée ; le message est pour le parent."""


@dataclass(frozen=True)
class Editable:
    """Un élément du matériel que le parent peut corriger, tel qu'il est enregistré."""

    kind: Kind
    index: int
    text: str  # énoncé, affirmation, texte à trous, gauche de l'association, recto
    answer: str | None = None  # bonne réponse du QCM, droite de l'association, verso
    distractors: list[str] = field(default_factory=list)  # mauvaises réponses du QCM
    answers: list[str] = field(default_factory=list)  # réponses acceptées du texte à trous
    true: bool | None = None  # affirmation vraie ou fausse


@dataclass(frozen=True)
class Edit:
    """La correction du parent : `before` est le texte qu'il a corrigé (contrôle que l'élément
    n'a pas changé entre-temps, par une correction de l'IA par exemple)."""

    kind: Kind
    index: int
    before: str
    text: str
    answer: str | None = None
    distractors: Sequence[str] = ()
    answers: Sequence[str] = ()
    true: bool | None = None


def _statements(material: KnowledgeMaterial) -> list[tuple[str, bool]]:
    return [(s, True) for s in material.true_statements] + [(s, False) for s in material.false_statements]


def editables(material: KnowledgeMaterial) -> list[Editable]:
    """Tout ce que le parent peut corriger dans le matériel d'une notion, dans l'ordre affiché."""
    found = [
        Editable("question", i, q.stem, q.answer, list(q.distractors))
        for i, q in enumerate(material.questions)
        if not q.generated and q.source is None  # calculée par le code, ou tirée d'un site
    ]
    found += [Editable("statement", i, s, true=t) for i, (s, t) in enumerate(_statements(material))]
    if material.cloze is not None:
        found.append(Editable("cloze", 0, material.cloze.text, answers=list(material.cloze.answers)))
    if material.pair is not None:
        found.append(Editable("pair", 0, material.pair.left, material.pair.right))
    if material.flashcard is not None:
        found.append(Editable("flashcard", 0, material.flashcard.front, material.flashcard.back))
    return found


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def apply_edit(material: KnowledgeMaterial, edit: Edit) -> KnowledgeMaterial:
    """Le matériel corrigé, validé par son schéma ; `EditError` si la correction ne va pas."""
    current = next((e for e in editables(material) if e.kind == edit.kind and e.index == edit.index), None)
    if current is None or _clean(current.text) != _clean(edit.before):
        raise EditError("Cette question a changé entre-temps : rouvrez la leçon et recommencez.")
    text = _clean(edit.text)
    if not text:
        raise EditError("Le texte ne peut pas être vide.")
    data = material.model_dump()
    match edit.kind:
        case "question":
            answer = _clean(edit.answer)
            wrong = [_clean(d) for d in edit.distractors if _clean(d)]
            if not answer:
                raise EditError("Écrivez la bonne réponse.")
            if len(wrong) != 3:
                raise EditError("Il faut trois mauvaises réponses.")
            if len({normalize(w) for w in wrong} | {normalize(answer)}) != 4:
                raise EditError("Les quatre réponses doivent être différentes.")
            question = data["questions"][edit.index]
            # Les erreurs typiques des anciennes mauvaises réponses ne valent plus.
            same = wrong == question["distractors"]
            question.update(stem=text, answer=answer, distractors=wrong)
            if not same:
                question["misconceptions"] = []
        case "statement":
            if edit.true is None:
                raise EditError("Dites si l'affirmation est vraie ou fausse.")
            statements = _statements(material)
            statements[edit.index] = (text, edit.true)
            data["true_statements"] = [s for s, t in statements if t]
            data["false_statements"] = [s for s, t in statements if not t]
        case "cloze":
            answers = [_clean(a) for a in edit.answers if _clean(a)]
            if text.count("___") != 1:
                raise EditError("Le texte à trous doit contenir un seul « ___ ».")
            if not answers:
                raise EditError("Écrivez au moins une réponse acceptée.")
            data["cloze"] = {"text": text, "answers": answers}
        case "pair":
            if not _clean(edit.answer):
                raise EditError("Écrivez les deux côtés de l'association.")
            data["pair"] = {"left": text, "right": _clean(edit.answer)}
        case "flashcard":
            if not _clean(edit.answer):
                raise EditError("Écrivez le recto et le verso de la carte.")
            data["flashcard"] = {"front": text, "back": _clean(edit.answer)}
    try:
        return KnowledgeMaterial.model_validate(data)
    except ValidationError as exc:
        raise EditError("Cette correction n'est pas valable (texte trop long ?).") from exc


def locate(material: KnowledgeMaterial, activity: BuiltActivity) -> Editable | None:
    """L'élément du matériel dont vient l'activité (pour corriger une question signalée par
    l'enfant), ou None (question calculée par le code, jeu fait de plusieurs éléments…)."""
    payload, found = activity.payload, editables(material)

    def first(kind: Kind, text: object) -> Editable | None:
        wanted = normalize(str(text or ""))
        return next((e for e in found if e.kind == kind and normalize(e.text) == wanted), None)

    match activity.type:
        case ActivityCode.MCQ:
            hit = first("question", payload.get("prompt"))
            if hit is None:  # QCM inversé ou « relier » : l'énoncé est reformulé, les choix restent
                shown = {normalize(str(c.get("text", ""))) for c in payload.get("choices", [])}
                hit = next(
                    (
                        e
                        for e in found
                        if e.kind == "question"
                        and {normalize(x) for x in (e.answer or "", *e.distractors)} == shown
                    ),
                    None,
                )
            return hit
        case ActivityCode.TRUE_FALSE:
            return first("statement", payload.get("statement"))
        case ActivityCode.FILL_BLANK:
            return first("cloze", payload.get("text"))
        case ActivityCode.FLASHCARD:
            return first("flashcard", payload.get("front"))
    return None
