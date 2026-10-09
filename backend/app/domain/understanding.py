"""Niveaux de compréhension et niveau de maîtrise affiché (spécification technique §5.1 à §5.3).

Réussir cinq QCM prouve que l'enfant *reconnaît* une notion, pas qu'il sait la *retrouver*
seul ni l'*appliquer* (cahier des charges complet §15, §65). Chaque activité sollicite donc
un niveau de compréhension, et une notion n'est « maîtrisée » que lorsque tous les niveaux
que la leçon permet de travailler ont été validés.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Literal

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeType, KnowledgeUnit
from app.domain.mastery import KNOWN_SCORE, MAX_BOX, Mastery


class CognitiveLevel(IntEnum):
    RECOGNIZE = 1  # reconnaître la bonne réponse parmi d'autres
    RECALL = 2  # retrouver la réponse sans la voir
    APPLY = 3  # utiliser une règle, une formule, une méthode
    EXPLAIN = 4  # expliquer pourquoi (question ouverte)
    TRANSFER = 5  # réutiliser dans une situation nouvelle (question ouverte)


LEVEL_NAMES = {
    CognitiveLevel.RECOGNIZE: "reconnaître",
    CognitiveLevel.RECALL: "se rappeler",
    CognitiveLevel.APPLY: "appliquer",
    CognitiveLevel.EXPLAIN: "expliquer",
    CognitiveLevel.TRANSFER: "transférer",
}

# Notions qui s'appliquent : on attend de l'enfant qu'il s'en serve, pas seulement qu'il les récite.
APPLICABLE = frozenset({KnowledgeType.RULE, KnowledgeType.FORMULA, KnowledgeType.PROCESS})


RECALLED = frozenset(
    {
        ActivityCode.FILL_BLANK,
        ActivityCode.FLASHCARD,
        ActivityCode.RANDOM_CARDS,
        ActivityCode.ORDER,
        ActivityCode.CLASSIFY,
        ActivityCode.COLORING,
    }
)


def cognitive_level(code: ActivityCode | str, difficulty: int) -> CognitiveLevel:
    """Niveau sollicité par une activité.

    Question ouverte : niveau 3, 4 ou 5 selon la question. QCM de difficulté 3 : la question
    demande de relier ou d'appliquer (§6.3 V1) ; texte à trous
    et carte mémoire, remettre dans l'ordre, ranger dans les cases, colorier selon une légende :
    l'enfant doit retrouver la réponse sans la voir ; tout le reste (QCM, vrai/faux, association,
    frise, memory, carte, défi rapide) : reconnaître.
    """
    code = ActivityCode(code)
    if code is ActivityCode.OPEN_QUESTION:
        return CognitiveLevel(min(5, difficulty + 2))  # difficulté 1, 2, 3 → appliquer, expliquer, transférer
    if code in (ActivityCode.COLUMN_OP, ActivityCode.CONJUGATION, ActivityCode.HOMOPHONE):
        return CognitiveLevel.APPLY  # poser et calculer, conjuguer, choisir le bon homophone
    if code in (ActivityCode.NUMBER_LINE, ActivityCode.FRACTION_BAR):
        # Lire (difficulté 2) : reconnaître ; placer ou colorier : appliquer.
        return CognitiveLevel.RECOGNIZE if difficulty == 2 else CognitiveLevel.APPLY
    if code in (ActivityCode.MCQ, ActivityCode.ALIGN) and difficulty >= 3:
        return CognitiveLevel.APPLY  # QCM « relier » ; points alignés avec deux points donnés
    if code in RECALLED:
        return CognitiveLevel.RECALL  # remettre les étapes, ranger ou colorier : sans les voir rangés
    return CognitiveLevel.RECOGNIZE


def ceiling(knowledge_type: KnowledgeType | str) -> CognitiveLevel:
    """Niveau le plus élevé exigé pour « maîtrisée ». Expliquer et transférer approfondissent une
    notion déjà maîtrisée (questions ouvertes) sans être exigés."""
    return CognitiveLevel.APPLY if KnowledgeType(knowledge_type) in APPLICABLE else CognitiveLevel.RECALL


def required_levels(unit: KnowledgeUnit, registry: ActivityRegistry) -> frozenset[int]:
    """Niveaux à valider pour que la notion soit maîtrisée.

    Ce sont les niveaux que le matériel de la leçon permet vraiment de travailler, jusqu'au
    plafond du type de notion : on n'exige jamais un niveau qu'aucune activité ne peut prouver.
    """
    levels = {cognitive_level(code, difficulty) for code, difficulty in registry.single_options(unit)}
    if any(t.multi_knowledge and t.accepts(unit) for t in registry.all()):
        levels.add(CognitiveLevel.RECOGNIZE)
    top = ceiling(unit.type)
    kept = frozenset(int(level) for level in levels if level <= top)
    return kept or frozenset({int(CognitiveLevel.RECOGNIZE)})


# --------------------------------------------------------------------------- #
# Niveau de maîtrise affiché (0 à 5)
# --------------------------------------------------------------------------- #


class MasteryLevel(IntEnum):
    NEVER = 0
    DISCOVERED = 1
    FRAGILE = 2
    LEARNING = 3
    MASTERED = 4
    SOLID = 5


LEVEL_LABELS = {
    MasteryLevel.NEVER: "Jamais travaillée",
    MasteryLevel.DISCOVERED: "Découverte",
    MasteryLevel.FRAGILE: "Fragile",
    MasteryLevel.LEARNING: "En cours d'acquisition",
    MasteryLevel.MASTERED: "Maîtrisée",
    MasteryLevel.SOLID: "Très bien maîtrisée",
}

Color = Literal["grey", "red", "orange", "green"]


def level_color(level: int) -> Color:
    """🟢 maîtrisée, 🟠 en cours, 🔴 découverte ou fragile, ⚪ jamais travaillée."""
    if level >= MasteryLevel.MASTERED:
        return "green"
    if level == MasteryLevel.LEARNING:
        return "orange"
    return "red" if level > MasteryLevel.NEVER else "grey"


@dataclass(frozen=True)
class NotionLevel:
    level: MasteryLevel
    missing: frozenset[int]  # niveaux de compréhension exigés et pas encore validés
    explanation: str

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self.level]

    @property
    def color(self) -> Color:
        return level_color(self.level)


def notion_level(
    mastery: Mastery | None, required: Iterable[int], now: datetime | None = None
) -> NotionLevel:
    """Niveau 0 à 5 d'une notion, et la phrase qui l'explique au parent (§42 du cahier des charges).

    | 0 | aucune réponse |
    | 1 | score < 30 |
    | 2 | score 30 à 49 |
    | 3 | score 50 à 79, ou ≥ 80 sans tous les niveaux exigés |
    | 4 | score ≥ 80 et tous les niveaux exigés validés |
    | 5 | niveau 4, score ≥ 90, et tenu jusqu'à la dernière boîte de révision (J+14) |

    Avec `now` (§130) : une notion sans doute en partie oubliée depuis sa dernière révision le
    dit, et n'est plus « très bien maîtrisée » (elle redevient « maîtrisée »).
    """
    level = _notion_level(mastery, frozenset(required))
    if now is None or mastery is None or level.level < MasteryLevel.LEARNING or not mastery.fading(now):
        return level
    days = math.floor(mastery.days_since(now))
    return NotionLevel(
        min(level.level, MasteryLevel.MASTERED),
        level.missing,
        f"Pas revue depuis {days} jours : sans doute un peu oubliée, la prochaine révision le vérifiera.",
    )


def _notion_level(mastery: Mastery | None, needed: frozenset[int]) -> NotionLevel:
    if mastery is None:
        return NotionLevel(MasteryLevel.NEVER, needed, "Pas encore travaillée.")
    missing = needed - mastery.levels
    if mastery.score < 30:
        return NotionLevel(MasteryLevel.DISCOVERED, missing, "Encore beaucoup d'erreurs : à reprendre.")
    if mastery.score < 50:
        return NotionLevel(MasteryLevel.FRAGILE, missing, "Des réussites, mais encore fragile.")
    if mastery.score < 80 or missing:
        return NotionLevel(MasteryLevel.LEARNING, missing, _learning_explanation(mastery, missing))
    if mastery.score >= KNOWN_SCORE and mastery.box == MAX_BOX:
        return NotionLevel(MasteryLevel.SOLID, missing, "Maîtrisée et bien retenue dans le temps.")
    return NotionLevel(MasteryLevel.MASTERED, missing, "Maîtrisée : il reste à la garder en mémoire.")


def _learning_explanation(mastery: Mastery, missing: frozenset[int]) -> str:
    if mastery.score < 80 or not missing:
        return "Souvent réussie, avec encore quelques erreurs."
    lowest = min(missing)
    if lowest == CognitiveLevel.RECOGNIZE:
        return "Bien retenue, à vérifier aussi dans les questions à choix."
    if lowest == CognitiveLevel.RECALL:
        return "Reconnaît la bonne réponse, pas encore la retrouver seul."
    return "Connaît la règle, doit encore s'entraîner à l'appliquer."


def skill_level(notion_levels: Iterable[int]) -> MasteryLevel:
    """Niveau d'une compétence : moyenne des niveaux de ses notions, arrondie vers le bas, et au
    plus un niveau au-dessus de sa notion la plus faible.

    Une compétence n'est donc maîtrisée que si ses notions le sont presque toutes, et une seule
    notion fragile suffit à la laisser « en cours d'acquisition ».
    """
    levels = list(notion_levels)
    if not levels:
        return MasteryLevel.NEVER
    return MasteryLevel(min(math.floor(sum(levels) / len(levels)), min(levels) + 1))
