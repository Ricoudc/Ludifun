"""Difficulté dynamique, notion par notion (cahier des charges §36).

La difficulté d'une activité de révision part du score de maîtrise (§8.3 ; l'oubli estimé, lui,
décide de l'ordre des notions), puis s'ajuste aux dernières réponses de l'enfant sur cette
notion :

- **monter** : les dernières réponses au niveau le plus difficile proposé sont réussies sans aide
  (`difficulty.step_up_after`, une de moins si elles sont rapides) ;
- **descendre** : les dernières réponses à ce niveau sont des échecs qui disent « ne sait pas
  encore » (connaissance, méthode, confusion, oubli) ; une erreur de lecture, de consigne ou
  une réponse au hasard ne fait pas baisser la difficulté : c'est l'attention qui manque, pas le
  niveau.

Pur et déterministe ; la décision et ses faits sont enregistrés avec l'activité (§126).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.errors import ErrorType
from app.domain.mastery import Mastery
from app.domain.rules import RULES

STEP_UP_AFTER = RULES.difficulty.step_up_after
STEP_DOWN_AFTER = RULES.difficulty.step_down_after
WINDOW = RULES.difficulty.window  # réponses regardées par notion
QUICK_SHARE = RULES.bonus.max_time_share  # réponse « rapide » : moins de cette part du temps prévu
SUCCESS = RULES.difficulty.success  # résultat d'une réponse réussie
FAILURE = RULES.adaptation.failure_below  # résultat en dessous duquel une réponse est un échec
MIN_DIFFICULTY, MAX_DIFFICULTY = 1, 3

# Erreurs qui disent que l'enfant ne sait pas encore faire : la difficulté peut baisser.
LEVEL_ERRORS = frozenset(
    {ErrorType.KNOWLEDGE, ErrorType.METHOD, ErrorType.CONFUSION, ErrorType.FORGOTTEN, ErrorType.CALCULATION}
)


@dataclass(frozen=True)
class RecentAnswer:
    """Une réponse récente sur la notion, la plus récente en dernier."""

    difficulty: int
    result: float  # résultat pour la notion, déjà réduit par l'aide (0 à 1)
    helped: bool = False  # aide demandée avant de répondre
    quick: bool = False  # nettement plus rapide que le temps prévu
    error_type: str | None = None


def by_score(score: int) -> tuple[int, ...]:
    """Difficultés selon le score (§8.3), par ordre de préférence."""
    if score < 50:
        return (1,)
    if score < 80:
        return (2, 1)
    return (3, 2)


@dataclass(frozen=True)
class Difficulty:
    preferred: tuple[int, ...]
    adjust: str | None = None  # « up », « down », ou None
    facts: dict[str, int] | None = None


def notion_difficulty(mastery: Mastery | None, recent: Sequence[RecentAnswer]) -> Difficulty:
    """Les difficultés à proposer pour une notion, la préférée d'abord."""
    if mastery is None:
        return Difficulty((1,))
    base = by_score(mastery.score)
    top = base[0]
    at_top = [a for a in recent if a.difficulty >= top]
    successes = 0
    for answer in reversed(at_top):
        if answer.result < SUCCESS or answer.helped:
            break
        successes += 1
    quick = successes > 0 and all(a.quick for a in at_top[-successes:])
    needed = STEP_UP_AFTER - 1 if quick else STEP_UP_AFTER
    if top < MAX_DIFFICULTY and successes >= needed:
        return Difficulty((top + 1, top), "up", {"successes": successes, "target": top + 1})
    failures = 0
    for answer in reversed([a for a in recent if a.difficulty <= top]):
        if answer.result >= FAILURE:
            break
        if answer.error_type is not None and answer.error_type not in LEVEL_ERRORS:
            break  # lecture, consigne, hasard : pas une question de niveau
        failures += 1
    if top > MIN_DIFFICULTY and failures >= STEP_DOWN_AFTER:
        return Difficulty((top - 1,), "down", {"failures": failures, "target": top - 1})
    return Difficulty(base)
