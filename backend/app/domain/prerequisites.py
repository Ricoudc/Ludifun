"""Revenir sur une connaissance préalable (§5.72, règles 1.16.0).

Quand l'enfant échoue deux fois sur une notion, l'erreur vient souvent d'avant : une division
ratée parce que les tables de multiplication ne sont pas sues, un accord raté parce que le verbe
n'est pas reconnu. Avant de reprendre la notion, le moteur revient sur une notion préalable de la
même leçon, si l'enfant ne la maîtrise pas encore.

D'où vient le lien « préalable » (jamais de l'IA pendant la séance) :
1. l'analyse a noté que la notion ratée est un exemple d'une autre (`example_of`) : la règle
   générale d'abord ;
2. sinon, une carte écrite à la main entre les thèmes (§5.47) : la division demande la
   multiplication et la soustraction, les fractions la division, la conjugaison de savoir
   reconnaître le verbe…

Parmi les notions possibles, la moins maîtrisée (une notion jamais travaillée compte pour 0),
puis la plus importante.
"""

from collections.abc import Mapping, Sequence

from app.domain.knowledge import KnowledgeUnit, RelationType, Theme
from app.domain.mastery import Mastery

# Thème → thèmes qu'il faut savoir avant (programme de l'école et du collège).
THEME_PREREQUISITES: dict[Theme, tuple[Theme, ...]] = {
    Theme.SUBTRACTION: (Theme.ADDITION,),
    Theme.DOUBLE: (Theme.ADDITION,),
    Theme.MULTIPLICATION: (Theme.ADDITION, Theme.DOUBLE),
    Theme.DIVISION: (Theme.MULTIPLICATION, Theme.SUBTRACTION),
    Theme.COMPARE: (Theme.PLACE_VALUE,),
    Theme.FRACTIONS: (Theme.DIVISION,),
    Theme.DECIMALS: (Theme.PLACE_VALUE, Theme.FRACTIONS),
    Theme.PERCENT: (Theme.FRACTIONS, Theme.PROPORTION),
    Theme.PROPORTION: (Theme.MULTIPLICATION, Theme.DIVISION),
    Theme.PERIMETER: (Theme.ADDITION, Theme.LENGTHS),
    Theme.AREA: (Theme.MULTIPLICATION, Theme.LENGTHS),
    Theme.PRIORITY: (Theme.ADDITION, Theme.MULTIPLICATION),
    Theme.POWERS: (Theme.MULTIPLICATION,),
    Theme.EQUATIONS: (Theme.PRIORITY, Theme.SUBTRACTION),
    Theme.PYTHAGORE: (Theme.POWERS, Theme.AREA),
    Theme.MONEY: (Theme.ADDITION,),
    Theme.CONJUGATION: (Theme.WORD_NATURE,),
    Theme.HOMOPHONES: (Theme.WORD_NATURE,),
    Theme.NUMBER: (Theme.WORD_NATURE,),
    Theme.GENDER: (Theme.WORD_NATURE,),
}


def _candidates(unit: KnowledgeUnit, units: Sequence[KnowledgeUnit]) -> list[KnowledgeUnit]:
    others = [u for u in units if u.id != unit.id]
    general = {r.target for r in unit.item.relations if r.type == RelationType.EXAMPLE_OF}
    by_relation = [u for u in others if u.id in general]
    if by_relation:
        return by_relation
    theme = unit.item.theme
    needed = THEME_PREREQUISITES.get(theme, ()) if theme is not None else ()
    return [u for u in others if u.item.theme in needed]


def prerequisite_of(
    unit: KnowledgeUnit,
    units: Sequence[KnowledgeUnit],
    masteries: Mapping[str, Mastery],
    below: int,
) -> KnowledgeUnit | None:
    """La notion préalable à revoir avant `unit`, si l'enfant ne la maîtrise pas encore (score sous
    `below`) ; None sinon."""

    def score(u: KnowledgeUnit) -> int:
        mastery = masteries.get(u.id)
        return mastery.score if mastery is not None else 0

    weak = [u for u in _candidates(unit, units) if score(u) < below]
    return min(weak, key=lambda u: (score(u), -u.item.importance, units.index(u)), default=None)
