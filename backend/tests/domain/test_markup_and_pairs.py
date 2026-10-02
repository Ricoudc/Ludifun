"""Bugs vus sur téléphone : « 3<sup>e</sup> groupe » affiché tel quel, et une association où la
même phrase est des deux côtés (« Je prends mon cartable. » ↔ « Je prends mon cartable. »)."""

import random

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import default_registry
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, KnowledgeType, KnowledgeUnit, Pair
from app.domain.text import clean_markup, gives_away, strip_markup
from app.domain.validation import PAIR_REASON, validate_material


def test_markup_is_stripped() -> None:
    assert strip_markup("Le verbe manger est du 3<sup>e</sup> groupe.") == "Le verbe manger est du 3e groupe."
    assert strip_markup("un <b>nom</b>&nbsp;propre<br/>ici") == "un nom propre ici"
    assert strip_markup("le **verbe** et le ___") == "le verbe et le ___"  # le trou reste
    assert strip_markup("2 < 3 et 5 > 4") == "2 < 3 et 5 > 4"  # pas une balise
    assert clean_markup({"a": ["1<sup>er</sup>"], "n": 3}) == {"a": ["1er"], "n": 3}


def verb(kid: str = "k1") -> KnowledgeItem:
    return KnowledgeItem(
        id=kid,
        type=KnowledgeType.TERM,
        label="manger",
        statement="Le verbe manger est du 1er groupe.",
        importance=4,
        attributes={"definition": "verbe du 1er groupe"},
        source_excerpt="manger",
    )


def test_material_is_cleaned_and_giveaway_pairs_refused() -> None:
    checked = validate_material(
        verb(),
        {
            "explanation": "Manger finit par -er : 1<sup>er</sup> groupe.",
            "false_statements": ["Le verbe manger est du 3<sup>e</sup> groupe."],
            "pair": {"left": "Je prends mon cartable.", "right": "Je prends mon cartable."},
        },
    )
    material = checked.material
    assert material.false_statements == ["Le verbe manger est du 3e groupe."]
    assert material.explanation == "Manger finit par -er : 1er groupe."
    assert material.pair is None and [r.reason for r in checked.rejected] == [PAIR_REASON]

    assert gives_away("Tu", "Tu vois bien mieux avec tes nouvelles lunettes.")
    assert not gives_away("prendre", "Je prends mon cartable.")
    assert not gives_away("phrase", "suite de mots qui expriment une idée")


def unit(kid: str, left: str, right: str) -> KnowledgeUnit:
    item = verb(kid)
    material = KnowledgeMaterial(knowledge_id=kid, explanation="x", pair=Pair(left=left, right=right))
    return KnowledgeUnit(item=item, material=material)


def test_stored_giveaway_pairs_are_no_longer_played() -> None:
    """Leçons analysées avant le contrôle : la paire fautive est simplement écartée du jeu."""
    registry = default_registry()
    match = registry.get(ActivityCode.MATCH)
    bad = unit("k1", "Je prends mon cartable.", "Je prends mon cartable.")
    assert not match.accepts(bad)
    assert not registry.get(ActivityCode.FIND_MATCH).accepts(bad)
    # Un texte à gauche d'une paire et à droite d'une autre rendrait l'association ambiguë.
    crossed = [
        unit("k1", "voir", "percevoir avec les yeux"),
        unit("k2", "venir", "voir"),
        unit("k3", "a", "b"),
    ]
    assert not match.can_build(crossed, 2)
    good = [
        unit("k1", "voir", "percevoir avec les yeux"),
        unit("k2", "venir", "arriver"),
        unit("k3", "a", "b"),
    ]
    assert match.build(good, 2, random.Random(1)).payload["left"]
