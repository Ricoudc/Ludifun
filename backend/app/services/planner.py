"""IA 5 (règles) : choisir quoi faire réviser maintenant.

Les notions les plus fragiles et les plus importantes passent en premier, et
la difficulté des questions suit le niveau de maîtrise de l'enfant.
"""

import random
from dataclasses import dataclass

from app.models import Notion, Question
from app.services.mastery import target_difficulties


@dataclass(frozen=True)
class Mode:
    kinds: tuple[str, ...]
    size: int
    time_limit_s: int | None = None
    weak_only: bool = False


ALL_KINDS = ("qcm", "vrai_faux", "texte_a_trous", "flashcard", "association", "question_ouverte")

MODES: dict[str, Mode] = {
    "quiz_rapide": Mode(kinds=("qcm", "vrai_faux"), size=10),
    "entrainement": Mode(kinds=ALL_KINDS, size=10),
    "flashcards": Mode(kinds=("flashcard",), size=15),
    "defi": Mode(kinds=("qcm", "vrai_faux", "texte_a_trous"), size=10, time_limit_s=60),
    # Révision personnalisée : uniquement les notions pas encore maîtrisées.
    "revision": Mode(kinds=ALL_KINDS, size=8, weak_only=True),
}

IMPORTANCE_WEIGHT = {"essentielle": 3, "importante": 2, "complementaire": 1}


def notion_priority(notion: Notion, level: int) -> int:
    return (6 - level) * IMPORTANCE_WEIGHT.get(notion.importance, 1)


def plan_session(
    mode_name: str,
    notions: list[Notion],
    questions: list[Question],
    levels: dict[int, int],
    rng: random.Random | None = None,
) -> list[Question]:
    mode = MODES[mode_name]
    rng = rng or random.Random()

    pool: dict[int, list[Question]] = {}
    for q in questions:
        if q.kind in mode.kinds:
            pool.setdefault(q.notion_id, []).append(q)
    for qs in pool.values():
        rng.shuffle(qs)

    ranked = [n for n in notions if n.id in pool]
    if mode.weak_only:
        ranked = [n for n in ranked if levels.get(n.id, 0) < 4] or ranked
    ranked.sort(key=lambda n: notion_priority(n, levels.get(n.id, 0)), reverse=True)

    selected: list[Question] = []
    # Tours successifs sur les notions : chaque notion reçoit une question par tour,
    # les plus prioritaires en premier, jusqu'à atteindre la taille de la séance.
    while len(selected) < mode.size and any(pool.get(n.id) for n in ranked):
        for notion in ranked:
            if len(selected) >= mode.size:
                break
            candidates = pool.get(notion.id)
            if not candidates:
                continue
            wanted = target_difficulties(levels.get(notion.id, 0))
            pick = next((q for q in candidates if q.difficulty in wanted), candidates[0])
            candidates.remove(pick)
            selected.append(pick)
    return selected
