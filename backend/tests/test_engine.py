import random
from datetime import datetime

from app.ai.client import FakeLLM
from app.models import Notion, Question
from app.services import mastery
from app.services.evaluator import evaluate, normalize
from app.services.planner import plan_session


def make_question(**kw) -> Question:
    base = dict(id=1, lesson_id=1, notion_id=1, kind="qcm", difficulty=1, prompt="?", choices=[],
                answer="", explanation="Explication.", pairs=[])
    return Question(**{**base, **kw})


def test_normalize_ignores_accents_and_case():
    assert normalize("  États-Généraux. ") == normalize("etats-generaux")


def test_fill_in_blank_tolerates_typo():
    q = make_question(kind="texte_a_trous", prompt="La ___ française", answer="Révolution")
    assert evaluate(q, "revolusion", FakeLLM(), "CM1").correct
    assert not evaluate(q, "Bastille", FakeLLM(), "CM1").correct


def test_association_partial_score():
    q = make_question(kind="association", answer="-", pairs=[
        {"left": "Louis XVI", "right": "Roi"},
        {"left": "Bastille", "right": "Prison"},
    ])
    result = evaluate(q, '{"Louis XVI": "Roi", "Bastille": "Roi"}', FakeLLM(), "CM1")
    assert result.score == 0.5
    assert not result.correct


def test_open_answer_uses_llm_evaluation():
    q = make_question(kind="question_ouverte", prompt="Pourquoi 1789 ?",
                      answer="Les États généraux sont réunis et le peuple prend la Bastille.")
    good = evaluate(q, "le peuple prend la bastille et les etats generaux sont reunis", FakeLLM(), "CM1")
    bad = evaluate(q, "je ne sais pas", FakeLLM(), "CM1")
    assert good.correct and not bad.correct
    assert bad.missing_points


def test_mastery_progression():
    assert mastery.next_level(0, 1.0) == 3
    assert mastery.next_level(0, 0.2) == 1
    assert mastery.next_level(3, 0.9) == 4
    assert mastery.next_level(5, 1.0) == 5
    assert mastery.next_level(2, 0.1) == 1
    assert mastery.next_level(1, 0.0) == 1
    now = datetime(2026, 1, 1)
    assert (mastery.next_review(4, now) - now).days == 7


def test_planner_prioritizes_weak_essential_notions():
    notions = [
        Notion(id=1, lesson_id=1, label="A", kind="date", content="", importance="essentielle"),
        Notion(id=2, lesson_id=1, label="B", kind="date", content="", importance="complementaire"),
    ]
    questions = [
        make_question(id=10 + i, notion_id=n, difficulty=d)
        for i, (n, d) in enumerate([(1, 1), (1, 3), (1, 4), (2, 1), (2, 3), (2, 4)])
    ]
    picked = plan_session("quiz_rapide", notions, questions, {1: 0, 2: 5}, random.Random(0))
    assert picked[0].notion_id == 1
    assert picked[0].difficulty == 1  # notion jamais vue → question facile
    assert picked[1].notion_id == 2
    assert picked[1].difficulty in (3, 4)  # notion maîtrisée → question difficile


def test_revision_mode_skips_mastered_notions():
    notions = [
        Notion(id=1, lesson_id=1, label="A", kind="date", content="", importance="essentielle"),
        Notion(id=2, lesson_id=1, label="B", kind="date", content="", importance="essentielle"),
    ]
    questions = [make_question(id=i, notion_id=1 + i % 2) for i in range(6)]
    picked = plan_session("revision", notions, questions, {1: 2, 2: 5}, random.Random(0))
    assert {q.notion_id for q in picked} == {1}
