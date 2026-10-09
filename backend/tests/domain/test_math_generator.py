"""Exercices de maths créés par le calcul : la réponse est recalculée ici, indépendamment du
générateur ; les nombres suivent la classe ; les mauvaises réponses sont des erreurs typiques."""

import re
from fractions import Fraction

import pytest

from app.domain.errors import ErrorType
from app.domain.knowledge import Grade, KnowledgeItem, MaterialQuestion
from app.domain.math_generator import PER_DIFFICULTY, Topic, fmt, generated_questions, topics


def notion(label: str, statement: str = "", key: str = "k1") -> KnowledgeItem:
    return KnowledgeItem(
        id=key,
        type="rule",
        label=label,
        statement=statement or f"{label}.",
        importance=4,
        attributes={"statement": statement or label, "example": label},
        source_excerpt=label,
    )


def number(text: str) -> Fraction:
    """« 12 345,5 » → 24691/2."""
    return Fraction(text.replace(" ", "").replace(" ", "").replace(",", "."))


def evaluate(expression: str) -> Fraction:
    """Le calcul de l'énoncé, refait ici avec les règles de priorité de Python."""
    python = expression.replace("×", "*").replace("÷", "/").replace("−", "-").replace(" ", "")
    python = re.sub(r"(\d+),(\d+)", r"Fraction('\1.\2')", python)
    python = re.sub(r"(?<![\w.'])(\d+)(?![\w.'])", r"Fraction(\1)", python)
    value = eval(python, {"Fraction": Fraction})  # énoncé écrit par le générateur, pas par un utilisateur
    assert isinstance(value, Fraction)
    return value


def check(question: MaterialQuestion) -> None:
    """La réponse est juste et les trois mauvaises réponses sont fausses (§117)."""
    stem, answer = question.stem, question.answer
    assert len(set(question.distractors)) == 3 and answer not in question.distractors
    assert len(question.misconceptions) == 3
    assert all(m in set(ErrorType) for m in question.misconceptions)
    assert question.generated and question.source is None
    if m := re.fullmatch(r"Combien font les (\d+)/(\d+) de ([\d ]+) \?", stem):
        expected = Fraction(int(m[1]), int(m[2])) * number(m[3])
    elif m := re.fullmatch(r"Combien font (\d+) % de ([\d ]+) \?", stem):
        expected = Fraction(int(m[1]), 100) * number(m[2])
    elif m := re.fullmatch(r"Combien font (.+) \?", stem):
        expected = evaluate(m[1])
    elif m := re.fullmatch(r"Combien vaut (\d+)\^(\d+) \?", stem):
        expected = Fraction(int(m[1]) ** int(m[2]))
    elif m := re.fullmatch(r"Quel est le (double|la moitié) de ([\d ]+) \?", stem):
        expected = number(m[2]) * 2
    elif m := re.fullmatch(r"Quelle est la moitié de ([\d ]+) \?", stem):
        expected = number(m[1]) / 2
    elif m := re.fullmatch(r"Quel est le plus grand nombre : (.+) \?", stem):
        expected = max(number(v) for v in m[1].split(", "))
        assert all(number(d) < expected for d in question.distractors)
    elif m := re.fullmatch(r"Quelle fraction est la plus grande : (.+) \?", stem):
        values = [Fraction(*map(int, v.split("/"))) for v in m[1].split(", ")]
        assert Fraction(*map(int, answer.split("/"))) == max(values)
        return
    elif m := re.fullmatch(r"Dans ([\d ]+), quel est le chiffre des (\w+) \?", stem):
        digits = m[1].replace(" ", "")
        position = ("unités", "dizaines", "centaines", "milliers").index(m[2])
        assert answer == digits[len(digits) - 1 - position]
        return
    elif m := re.fullmatch(r"Quel est le périmètre d'un carré de (\d+) cm de côté \?", stem):
        expected = Fraction(4 * int(m[1]))
    elif m := re.fullmatch(
        r"Quel est le périmètre d'un rectangle de (\d+) cm de long et (\d+) cm de large \?", stem
    ):
        expected = Fraction(2 * (int(m[1]) + int(m[2])))
    elif m := re.fullmatch(
        r"Quelle est l'aire d'un rectangle de (\d+) cm de long et (\d+) cm de large \?", stem
    ):
        expected = Fraction(int(m[1]) * int(m[2]))
    elif m := re.fullmatch(r"(\d+) .+ coûtent (\d+) €\. Combien coûtent (\d+) .+ \?", stem):
        expected = Fraction(int(m[2]), int(m[1])) * int(m[3])
    elif m := re.fullmatch(r"Quelle est la solution de l'équation (\d*)x \+ (\d+) = (\d+) \?", stem):
        a = int(m[1] or 1)
        x = int(answer.removeprefix("x = "))
        assert a * x + int(m[2]) == int(m[3])
        assert all(
            a * int(d.removeprefix("x = ").replace(",", ".").split(".")[0]) + int(m[2]) != int(m[3])
            for d in question.distractors
        )
        return
    elif m := re.fullmatch(
        r"Un triangle ABC est rectangle en B, avec AB = (\d+) cm et BC = (\d+) cm\. Combien mesure AC \?",
        stem,
    ):
        assert number(answer.removesuffix(" cm")) ** 2 == int(m[1]) ** 2 + int(m[2]) ** 2
        return
    elif m := re.fullmatch(
        r"Un triangle ABC est rectangle en B, avec AC = (\d+) cm et AB = (\d+) cm\. Combien mesure BC \?",
        stem,
    ):
        assert number(answer.removesuffix(" cm")) ** 2 == int(m[1]) ** 2 - int(m[2]) ** 2
        return
    else:
        pytest.fail(f"énoncé inconnu : {stem}")
    unit = re.sub(r"^[\d ,]+", "", answer)
    assert number(answer.removesuffix(unit)) == expected, stem
    assert all(number(d.removesuffix(unit)) != expected for d in question.distractors), stem


CASES = [
    ("La soustraction", Grade.CP, {Topic.SUB}),
    ("Les doubles et les moitiés", Grade.CP, {Topic.DOUBLE}),
    ("Les dizaines et les unités", Grade.CP, {Topic.PLACE}),
    ("Comparer et ranger des nombres", Grade.CE1, {Topic.COMPARE}),
    ("Les tables de multiplication", Grade.CE1, {Topic.MUL}),
    ("L'addition posée avec retenue", Grade.CE2, {Topic.ADD}),
    ("La division", Grade.CM1, {Topic.DIV}),
    ("Fraction d'une quantité", Grade.CM1, {Topic.FRACTION}),
    ("Multiplier un nombre décimal par 10, 100, 1000", Grade.CM2, {Topic.DECIMAL, Topic.MUL}),
    ("Proportionnalité", Grade.CM2, {Topic.PROPORTION}),
    ("Périmètre et aire du rectangle", Grade.CM2, {Topic.PERIMETER, Topic.AREA}),
    ("Les pourcentages", Grade.SIXIEME, {Topic.PERCENT}),
    ("Les priorités opératoires", Grade.CINQUIEME, {Topic.PRIORITY}),
    ("Les puissances", Grade.QUATRIEME, {Topic.POWER}),
    ("Résoudre une équation", Grade.TROISIEME, {Topic.EQUATION}),
    ("Le théorème de Pythagore", Grade.QUATRIEME, {Topic.PYTHAGORE}),
]


@pytest.mark.parametrize(("label", "grade", "expected"), CASES)
def test_every_answer_is_computed_right(label: str, grade: Grade, expected: set[Topic]) -> None:
    item = notion(label)
    assert set(topics(item, grade)) == expected
    questions = generated_questions(item, grade)
    # Bien plus que les 2 ou 3 questions d'une leçon photographiée, aux trois difficultés.
    assert len(questions) >= 10 and {q.difficulty for q in questions} == {1, 2, 3}
    assert len({q.stem for q in questions}) == len(questions)
    for question in questions:
        check(question)


@pytest.mark.parametrize("seed", range(30))
def test_many_notions_stay_right(seed: int) -> None:
    """Beaucoup de tirages (autre notion, autre graine) : toujours juste."""
    for label, grade, _ in CASES:
        for question in generated_questions(notion(label, key=f"k{seed}"), grade):
            check(question)


def test_numbers_follow_the_grade() -> None:
    def largest(grade: Grade) -> Fraction:
        stems = [q.stem for q in generated_questions(notion("L'addition"), grade)]
        return max(number(n) for s in stems for n in re.findall(r"\d[\d ]*", s))

    assert largest(Grade.CP) <= 20
    assert largest(Grade.CE1) <= 100
    assert largest(Grade.CM2) > 1000


def test_a_topic_is_only_used_from_its_grade() -> None:
    assert topics(notion("Le théorème de Pythagore"), Grade.CM1) == []
    assert topics(notion("Les pourcentages"), Grade.CE1) == []
    assert topics(notion("Les fractions"), Grade.CE2) == [Topic.FRACTION]


def test_a_notion_without_calculation_gets_nothing() -> None:
    assert generated_questions(notion("Les angles droits"), Grade.CM1) == []
    # Calcul mental sans opération précise : celles de la classe.
    assert topics(notion("Calcul mental"), Grade.CP) == [Topic.ADD, Topic.SUB]
    assert topics(notion("Calcul mental"), Grade.CE2) == [Topic.ADD, Topic.MUL]


def test_same_notion_same_questions_and_no_repeat() -> None:
    item = notion("Les tables de multiplication")
    first = generated_questions(item, Grade.CE2)
    assert first == generated_questions(item, Grade.CE2)
    assert first != generated_questions(notion("Les tables de multiplication", key="k2"), Grade.CE2)
    skipped = generated_questions(item, Grade.CE2, existing={first[0].stem})
    assert first[0].stem not in {q.stem for q in skipped}
    assert len([q for q in first if q.difficulty == 1]) == PER_DIFFICULTY


def test_typical_errors_are_named() -> None:
    area = next(
        q
        for q in generated_questions(notion("L'aire du rectangle"), Grade.CM1)
        if q.stem.startswith("Quelle est l'aire")
    )
    # Le périmètre à la place de l'aire : une confusion entre deux notions.
    length, width = map(int, re.findall(r"\d+", area.stem))
    assert area.misconception_of(f"{fmt(2 * (length + width))} cm²") == ErrorType.CONFUSION


def test_french_number_format() -> None:
    assert fmt(12345) == "12 345"
    assert fmt(Fraction(7, 2)) == "3,5"
    assert fmt(Fraction(10, 1)) == "10"
    assert fmt(899.5) == "899,5"
