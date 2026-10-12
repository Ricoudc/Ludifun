"""Confiance de chaque notion extraite (§115) : calculée par le code à partir de ce qui peut
faire douter ; les leçons de référence, bien lues, sont toutes en confiance élevée."""

from app.domain.confidence import Trust, notion_confidence
from tests.domain.conftest import LESSON_FILES, ReferenceLesson, load_lesson


def test_well_read_lessons_are_trusted() -> None:
    for name in LESSON_FILES:
        lesson = load_lesson(name)
        for unit in lesson.units.values():
            found = notion_confidence(unit.item, [("good", lesson.raw["ocr_text"])])
            assert found.value == 1.0 and found.trust is Trust.HIGH and not found.reasons, unit.id


def test_what_makes_a_notion_doubtful(history: ReferenceLesson) -> None:
    item = history.units["k1"].item  # « La Révolution française commence en 1789. »
    text = history.raw["ocr_text"]
    partial = notion_confidence(item, [("partial", text)])
    assert partial.value == 0.7 and partial.trust is Trust.MEDIUM
    assert partial.reasons == ("la page a été lue en partie",)
    # Une date absente de la leçon : l'IA l'a peut-être inventée ou mal lue.
    wrong_date = item.model_copy(update={"statement": "La Révolution française commence en 1798."})
    found = notion_confidence(wrong_date, [("good", text)])
    assert found.trust is Trust.MEDIUM and found.reasons == ("« 1798 » n'est écrit nulle part dans la leçon",)
    # Mal lue, et un mot illisible : on ne propose pas la notion sans confirmation.
    unreadable = item.model_copy(update={"statement": "La Révolution commence en [illisible]."})
    low = notion_confidence(unreadable, [("unreadable", text)])
    assert low.trust is Trust.LOW and "un mot du passage était illisible" in low.reasons
    # Le passage cité introuvable.
    elsewhere = item.model_copy(update={"source_excerpt": "Une phrase qui n'est pas dans la leçon du tout."})
    assert notion_confidence(elsewhere, [("good", text)]).reasons == (
        "le passage cité n'a pas été retrouvé dans la leçon",
    )
