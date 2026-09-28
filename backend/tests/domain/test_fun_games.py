"""Étape 25 : des jeux plus sympas que des quiz, et des consignes au niveau de l'enfant.

- l'IA peut proposer un jeu de tri ou « remettre dans l'ordre » pour n'importe quelle notion ;
- ces jeux sont contrôlés avant d'être gardés ;
- le moteur propose les jeux visuels avant un quiz (règle `visual_first`) ;
- chaque jeu a une consigne pour chaque cycle, et l'IA reçoit des règles d'écriture par classe.
"""

import random
from typing import Any

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.decisions import describe
from app.domain.instructions import cycle, instruction, writing_rules
from app.domain.knowledge import KnowledgeType, KnowledgeUnit
from app.domain.material_view import material_blocks
from app.domain.simulated_pupil import respond
from app.domain.validation import validate_material
from tests.domain.conftest import ReferenceLesson
from tests.domain.test_composer import NOW

NOUN_OR_VERB = {
    "prompt": "Range chaque mot : nom ou verbe ?",
    "categories": [
        {"name": "Nom", "members": ["chat", "table", "maison"]},
        {"name": "Verbe", "members": ["manger", "courir"]},
    ],
}
SMALL_TO_BIG = {"prompt": "Range du plus petit au plus grand.", "items": ["1/4", "2/4", "3/4"]}


def with_games(unit: KnowledgeUnit, **games: Any) -> KnowledgeUnit:
    raw = unit.material.model_dump(mode="json") | games
    validated = validate_material(unit.item, raw)
    assert validated.rejected == [], validated.rejected
    return KnowledgeUnit(item=unit.item, material=validated.material)


def test_games_proposed_by_the_ai_are_checked(math: ReferenceLesson) -> None:
    unit = math.unit("k1")
    good = validate_material(
        unit.item, {"explanation": "x", "sorting": NOUN_OR_VERB, "sequence": SMALL_TO_BIG}
    )
    assert good.material.sorting is not None and good.material.sequence is not None

    bad_sorting = [
        {"prompt": "Range", "categories": [{"name": "Nom", "members": ["chat", "table"]}]},  # une case
        {
            "prompt": "Range",
            "categories": [
                {"name": "Nom", "members": ["chat", "table"]},
                {"name": "Verbe", "members": ["chat", "courir"]},  # « chat » dans deux cases
            ],
        },
        {
            "prompt": "Range",
            "categories": [
                {"name": "Nom", "members": ["Verbe", "table"]},  # le nom d'une case
                {"name": "Verbe", "members": ["manger", "courir"]},
            ],
        },
        {
            "prompt": "Range",
            "categories": [
                {"name": "Nom", "members": ["a", "b", "c", "d", "e"]},  # trop d'éléments
                {"name": "Verbe", "members": ["manger", "courir"]},
            ],
        },
    ]
    for raw in bad_sorting:
        checked = validate_material(unit.item, {"explanation": "x", "sorting": raw})
        assert checked.material.sorting is None
        assert [r.element for r in checked.rejected] == ["sorting"]

    for items in (["1", "2"], ["1", "2", "2"], [str(i) for i in range(7)]):
        checked = validate_material(
            unit.item, {"explanation": "x", "sequence": {"prompt": "Ordre", "items": items}}
        )
        assert checked.material.sequence is None
        assert [r.element for r in checked.rejected] == ["sequence"]


def test_sorting_and_ordering_work_for_any_notion(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = with_games(math.unit("k1"), sorting=NOUN_OR_VERB, sequence=SMALL_TO_BIG)
    assert unit.type not in {KnowledgeType.CLASSIFICATION, KnowledgeType.PROCESS}

    classify = registry.get(ActivityCode.CLASSIFY)
    activity = classify.build([unit], 2, random.Random(1))
    assert activity.payload["prompt"] == "Range chaque mot : nom ou verbe ?"
    assert classify.grade(activity, respond(activity, lambda _: True)).score == 1
    assert classify.grade(activity, respond(activity, lambda _: False)).score < 1

    order = registry.get(ActivityCode.ORDER)
    activity = order.build([unit], 2, random.Random(1))
    assert activity.payload["prompt"] == "Range du plus petit au plus grand."
    assert activity.solution["display"] == "1/4 → 2/4 → 3/4"
    assert order.grade(activity, respond(activity, lambda _: True)).score == 1


def test_visual_games_come_before_quizzes(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = [with_games(u, sorting=NOUN_OR_VERB) if u.id == "k1" else u for u in math.units.values()]
    for seed in range(20):
        plan = SessionComposer(registry).compose(units, {}, NOW, seed)
        k1 = [p for p in plan.items if p.activity.knowledge_ids == ["k1"] and p.block.value == "core"]
        assert k1 and k1[0].activity.type == ActivityCode.CLASSIFY, seed
        assert k1[0].reason["facts"]["visual_first"] is True
        assert str(describe(k1[0].reason)).endswith("Jeu visuel proposé avant un quiz.")


def test_every_game_has_an_instruction_for_every_cycle() -> None:
    assert [cycle(g) for g in ("CP", "CE2", "CM1", "6e", "5e", "3e", None, "L3")] == [2, 2, 3, 3, 4, 4, 3, 3]
    for code in ActivityCode:
        texts = [instruction(code, grade) for grade in ("CP", "CM1", "4e")]
        assert all(texts) and len(set(texts)) == 3, code
        # Au CP, des phrases courtes.
        assert all(len(sentence.split()) <= 10 for sentence in str(texts[0]).split(". ")), code
    assert instruction("JEU_INCONNU", "CP") is None
    assert "12 mots" in writing_rules("CE1") and "cycle 4" in writing_rules("3e")


def test_the_parent_sees_every_question_with_its_answer(lesson: ReferenceLesson) -> None:
    for unit in lesson.units.values():
        blocks = material_blocks(unit.material)
        titles = [b.title for b in blocks]
        assert titles[-1] == "🆘 Aides" and all(b.lines for b in blocks)
        for question in unit.material.questions:
            assert any(question.stem in line and question.answer in line for b in blocks for line in b.lines)
        assert any(unit.material.explanation in line for line in blocks[-1].lines)
