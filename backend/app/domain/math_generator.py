"""Exercices de mathématiques créés par le calcul, à la classe de l'enfant.

Une leçon de maths photographiée ne donne souvent que deux ou trois questions. Le code reconnaît
le thème de chaque notion (addition, tables, fractions, aires, équations…) et crée autant de
questions qu'il faut : les nombres sont tirés selon la classe et la difficulté, **la réponse est
calculée** (jamais devinée), et les trois mauvaises réponses proposées sont les erreurs typiques
(oubli de la retenue, mauvaise opération, aire confondue avec le périmètre…), chacune avec son
type d'erreur pour le parent.

Déterministe : la même notion donne toujours la même réserve de questions ; le composeur évite
celles déjà posées aux séances précédentes. Aucune IA, aucun réseau.
"""

import math
import random
import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from app.domain.errors import ErrorType
from app.domain.knowledge import Grade, KnowledgeItem, KnowledgeMaterial, MaterialQuestion
from app.domain.text import normalize

PER_DIFFICULTY = 6  # questions créées par thème et par difficulté
MAX_TOPICS = 2  # thèmes retenus par notion
GRADES = list(Grade)


class Topic(StrEnum):
    ADD = "addition"
    SUB = "soustraction"
    MUL = "multiplication"
    DIV = "division"
    DOUBLE = "double et moitié"
    PLACE = "valeur des chiffres"
    COMPARE = "comparer des nombres"
    FRACTION = "fractions"
    DECIMAL = "nombres décimaux"
    PERCENT = "pourcentages"
    PROPORTION = "proportionnalité"
    PERIMETER = "périmètre"
    AREA = "aire"
    PRIORITY = "priorités opératoires"
    POWER = "puissances"
    EQUATION = "équations"
    PYTHAGORE = "théorème de Pythagore"
    CLOCK = "lire l'heure"  # jeu « Quelle heure est-il ? » (activité CLOCK), pas de QCM ici
    MONEY = "monnaie"  # jeu « Pièces et billets » (activité MONEY)


# Mots (sans accents) qui désignent chaque thème, et classe à partir de laquelle il est au programme.
_TOPICS: tuple[tuple[Topic, str, Grade], ...] = (
    (Topic.CLOCK, r"lire l heure|\bhorloge|\baiguilles?\b|\bpendule|\bheures? et minutes", Grade.CP),
    (Topic.MONEY, r"monnaie|\beuros?\b|centimes?|pieces? et (de )?billets|rendre la monnaie", Grade.CP),
    (Topic.PYTHAGORE, r"pythagore|hypotenuse", Grade.QUATRIEME),
    (Topic.EQUATION, r"equation|inconnue", Grade.QUATRIEME),
    (Topic.POWER, r"puissance|exposant", Grade.QUATRIEME),
    (Topic.PRIORITY, r"priorite|parenthese|enchainement", Grade.CINQUIEME),
    (Topic.PERCENT, r"pourcent|pour cent", Grade.CM2),
    (Topic.PROPORTION, r"proportionn|regle de trois|echelle", Grade.CM1),
    (Topic.PERIMETER, r"perimetre|contour", Grade.CE2),
    (Topic.AREA, r"\baire|surface", Grade.CM1),
    (Topic.FRACTION, r"fraction|numerateur|denominateur", Grade.CE2),
    (Topic.DECIMAL, r"decima|virgule|dixieme|centieme", Grade.CM1),
    (Topic.DIV, r"division|diviser|quotient|partag", Grade.CE2),
    (Topic.MUL, r"multipli|produit|\btables?\b|\bfois\b", Grade.CE1),
    (Topic.SUB, r"soustra|difference|retrancher|enlever", Grade.CP),
    (Topic.ADD, r"addition|additionner|\bsomme|ajouter", Grade.CP),
    (Topic.DOUBLE, r"\bdouble|moitie", Grade.CP),
    (Topic.PLACE, r"dizaine|centaine|unite|millier|decompos|chiffre des", Grade.CP),
    (Topic.COMPARE, r"compar|ranger|\bordre\b|plus grand|plus petit|inferieur|superieur", Grade.CP),
)
# Calcul mental, nombres, opérations : sans mot plus précis, les opérations de la classe.
_GENERIC = re.compile(r"calcul|operation|nombre")


def _rank(grade: Grade) -> int:
    return GRADES.index(grade)


def topics(item: KnowledgeItem, grade: Grade) -> list[Topic]:
    """Les thèmes de calcul de la notion, au programme de la classe (au plus `MAX_TOPICS`)."""
    text = normalize(item.corpus())
    found = [
        topic
        for topic, pattern, since in _TOPICS
        if re.search(pattern, text) and _rank(grade) >= _rank(since)
    ]
    if not found and _GENERIC.search(text):
        found = [Topic.ADD, Topic.SUB] if _rank(grade) <= _rank(Grade.CP) else [Topic.ADD, Topic.MUL]
    return found[:MAX_TOPICS]


# --------------------------------------------------------------------------- #
# Nombres selon la classe et la difficulté
# --------------------------------------------------------------------------- #

# Plus grand nombre manipulé, par classe ; la difficulté 1 en prend le dixième, la 2 le tiers.
_LIMIT = {
    Grade.CP: 20,
    Grade.CE1: 100,
    Grade.CE2: 1000,
    Grade.CM1: 10000,
    Grade.CM2: 100000,
    Grade.SIXIEME: 100000,
    Grade.CINQUIEME: 100000,
    Grade.QUATRIEME: 100000,
    Grade.TROISIEME: 100000,
}


def _limit(grade: Grade, difficulty: int) -> int:
    top = _LIMIT[grade]
    return max(10, {1: top // 10, 2: top // 3, 3: top}[difficulty])


def fmt(value: int | float | Fraction) -> str:
    """Écriture française : « 12 345 », « 3,5 »."""
    if isinstance(value, Fraction):
        value = value.numerator if value.denominator == 1 else float(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    whole, _, decimals = f"{value:.4f}".rstrip("0").partition(".")
    return f"{int(whole):,}".replace(",", " ") + ("," + decimals if decimals else "")


@dataclass(frozen=True)
class _Draft:
    stem: str
    answer: str
    wrong: list[tuple[str, ErrorType]]


def _question(draft: _Draft, difficulty: int) -> MaterialQuestion | None:
    """Trois mauvaises réponses différentes entre elles et de la bonne ; sinon pas de question."""
    distractors: list[str] = []
    errors: list[str | None] = []
    for text, error in draft.wrong:
        if text != draft.answer and text not in distractors and not text.startswith("-"):
            distractors.append(text)
            errors.append(error.value)
        if len(distractors) == 3:
            break
    if len(distractors) < 3:
        return None
    return MaterialQuestion(
        difficulty=difficulty,
        stem=draft.stem,
        answer=draft.answer,
        distractors=distractors,
        misconceptions=errors,
        generated=True,
    )


# --------------------------------------------------------------------------- #
# Un générateur par thème : (aléa, classe, difficulté) → question
# --------------------------------------------------------------------------- #

Maker = Callable[[random.Random, Grade, int], _Draft | None]
C, M, R, K = ErrorType.CALCULATION, ErrorType.METHOD, ErrorType.READING, ErrorType.KNOWLEDGE


def _add(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    top = _limit(grade, difficulty)
    a, b = rng.randint(1, top // 2), rng.randint(1, top // 2)
    s = a + b
    return _Draft(
        f"Combien font {fmt(a)} + {fmt(b)} ?",
        fmt(s),
        [(fmt(s - 10), C), (fmt(s + 1), C), (fmt(s - 1), C), (fmt(abs(a - b)), M), (fmt(s + 10), C)],
    )


def _sub(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    top = _limit(grade, difficulty)
    a = rng.randint(top // 4 + 2, top)
    b = rng.randint(1, a - 1)
    d = a - b
    # Erreur classique : « le plus petit chiffre ôté du plus grand » dans chaque colonne.
    digits = [
        abs(int(x) - int(y))
        for x, y in zip(str(a).zfill(len(str(a))), str(b).zfill(len(str(a))), strict=True)
    ]
    swapped = int("".join(map(str, digits)))
    return _Draft(
        f"Combien font {fmt(a)} − {fmt(b)} ?",
        fmt(d),
        [(fmt(swapped), M), (fmt(d + 10), C), (fmt(d + 1), C), (fmt(d - 1), C), (fmt(a + b), M)],
    )


def _mul(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    if difficulty == 1 or _rank(grade) <= _rank(Grade.CE2):
        a, b = rng.randint(2, 5 if difficulty == 1 else 9), rng.randint(2, 9)  # les tables
    elif difficulty == 2:
        a, b = rng.randint(11, 99), rng.randint(2, 9)
    else:
        a, b = rng.randint(12, 99), rng.randint(11, 49)
    p = a * b
    return _Draft(
        f"Combien font {fmt(a)} × {fmt(b)} ?",
        fmt(p),
        [(fmt(p + a), C), (fmt(p - b), C), (fmt(a + b), M), (fmt(p + 10), C), (fmt(p - a), C)],
    )


def _div(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    b = rng.randint(2, 9 if difficulty < 3 else 25)
    q = rng.randint(2, 10 if difficulty == 1 else 50 if difficulty == 2 else 200)
    a = b * q
    return _Draft(
        f"Combien font {fmt(a)} ÷ {fmt(b)} ?",
        fmt(q),
        [(fmt(q + 1), C), (fmt(q - 1), C), (fmt(a - b), M), (fmt(q * 10), C), (fmt(b), R)],
    )


def _double(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    n = rng.randint(2, max(10, _limit(grade, difficulty) // 2))
    if rng.random() < 0.5:
        return _Draft(
            f"Quel est le double de {fmt(n)} ?",
            fmt(2 * n),
            [(fmt(n + 2), M), (fmt(2 * n + 1), C), (fmt(2 * n - 2), C), (fmt(n // 2), M)],
        )
    n += n % 2
    return _Draft(
        f"Quelle est la moitié de {fmt(n)} ?",
        fmt(n // 2),
        [(fmt(n - 2), M), (fmt(2 * n), M), (fmt(n // 2 + 1), C), (fmt(n // 2 - 1), C)],
    )


_PLACES = ("unités", "dizaines", "centaines", "milliers")


def _place(rng: random.Random, grade: Grade, difficulty: int) -> _Draft | None:
    size = min(4, max(2, len(str(_limit(grade, difficulty))) - 1))
    digits = rng.sample(range(1, 10), size)
    number = int("".join(map(str, digits)))
    position = rng.randint(1, size - 1)  # pas les unités : trop facile
    answer = str(digits[size - 1 - position])
    return _Draft(
        f"Dans {fmt(number)}, quel est le chiffre des {_PLACES[position]} ?",
        answer,
        [(str(d), K) for d in digits if str(d) != answer]
        + [(str((int(answer) + k) % 10), K) for k in (1, 9)],
    )


def _compare(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    top = _limit(grade, difficulty)
    base = rng.randint(top // 10 + 10, max(top, top // 10 + 20))
    s = str(base)
    swapped = int(s[::-1]) if s[::-1][0] != "0" else base - 9
    near = [base, swapped, base - rng.randint(1, 9), base + rng.choice([-10, 10, -100, 100])]
    values = list(dict.fromkeys(v for v in near if v > 0))
    while len(values) < 4:
        values.append(values[-1] + rng.randint(1, 9))
    largest = max(values)
    shown = ", ".join(fmt(v) for v in rng.sample(values, len(values)))
    return _Draft(
        f"Quel est le plus grand nombre : {shown} ?",
        fmt(largest),
        [(fmt(v), K) for v in values if v != largest],
    )


def _fraction(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    if difficulty == 1:
        d = rng.choice([2, 3, 4, 5, 10])
        n = rng.randint(1, d - 1)
        others = [(n + k) % d or d for k in (1, 2, 3)]
        values = list(dict.fromkeys([n, *others]))
        largest = max(values)
        shown = ", ".join(f"{v}/{d}" for v in rng.sample(values, len(values)))
        return _Draft(
            f"Quelle fraction est la plus grande : {shown} ?",
            f"{largest}/{d}",
            [(f"{v}/{d}", K) for v in values if v != largest] + [(f"{d}/{largest}", K)],
        )
    d = rng.choice([2, 3, 4, 5, 6, 8, 10])
    n = rng.randint(1, d - 1)
    quantity = d * rng.randint(2, 6 if difficulty == 2 else 25)
    answer = quantity * n // d
    return _Draft(
        f"Combien font les {n}/{d} de {fmt(quantity)} ?",
        fmt(answer),
        [
            (fmt(quantity // d), M),
            (fmt(quantity * d // max(1, n)), M),
            (fmt(quantity - n), M),
            (fmt(answer + n), C),
        ],
    )


def _decimal(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    if difficulty == 1:
        a, b = Fraction(rng.randint(11, 99), 10), Fraction(rng.randint(11, 99), 10)
        s = a + b
        return _Draft(
            f"Combien font {fmt(a)} + {fmt(b)} ?",
            fmt(s),
            [(fmt(s + 1), C), (fmt(s - Fraction(1, 10)), C), (fmt(s * 10), K), (fmt(s + Fraction(1, 10)), C)],
        )
    value = Fraction(rng.randint(101, 9999), 100)
    factor = rng.choice([10, 100]) if difficulty == 2 else rng.choice([10, 100, 1000])
    answer = value * factor
    zero = fmt(value) + "0"  # « on ajoute un zéro » : l'erreur la plus fréquente
    return _Draft(
        f"Combien font {fmt(value)} × {fmt(factor)} ?",
        fmt(answer),
        [(zero, K), (fmt(value / factor), M), (fmt(answer * 10), C), (fmt(answer / 10), C)],
    )


def _percent(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    p = rng.choice(
        [10, 50, 25] if difficulty == 1 else [10, 20, 25, 50, 75] if difficulty == 2 else [5, 15, 30, 40, 60]
    )
    total = 20 * rng.randint(1, 10 if difficulty < 3 else 50)
    answer = Fraction(p * total, 100)
    return _Draft(
        f"Combien font {p} % de {fmt(total)} ?",
        fmt(answer),
        [(fmt(total - p), M), (fmt(answer * 10), C), (fmt(p), R), (fmt(answer + p), C), (fmt(answer * 2), C)],
    )


def _proportion(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    unit = rng.randint(2, 9 if difficulty < 3 else 25)
    first, second = rng.sample(range(2, 10 if difficulty < 3 else 20), 2)
    things = rng.choice(["cahiers", "stylos", "billets de cinéma", "croissants"])
    answer = unit * second
    return _Draft(
        f"{first} {things} coûtent {fmt(unit * first)} €. Combien coûtent {second} {things} ?",
        f"{fmt(answer)} €",
        [
            (f"{fmt(unit * first + (second - first))} €", M),  # « on ajoute la différence »
            (f"{fmt(unit * first * second)} €", M),
            (f"{fmt(answer + unit)} €", C),
            (f"{fmt(unit)} €", R),
        ],
    )


def _sides(rng: random.Random, difficulty: int) -> tuple[int, int]:
    top = {1: 10, 2: 30, 3: 120}[difficulty]
    length = rng.randint(3, top)
    width = rng.randint(2, max(2, length - 1))
    return length, width


def _perimeter(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    length, width = _sides(rng, difficulty)
    if difficulty == 1 or rng.random() < 0.3:
        return _Draft(
            f"Quel est le périmètre d'un carré de {length} cm de côté ?",
            f"{fmt(4 * length)} cm",
            [
                (f"{fmt(length * length)} cm", ErrorType.CONFUSION),
                (f"{fmt(2 * length)} cm", M),
                (f"{fmt(4 * length + 4)} cm", C),
            ],
        )
    return _Draft(
        f"Quel est le périmètre d'un rectangle de {length} cm de long et {width} cm de large ?",
        f"{fmt(2 * (length + width))} cm",
        [
            (f"{fmt(length + width)} cm", M),
            (f"{fmt(length * width)} cm", ErrorType.CONFUSION),
            (f"{fmt(2 * length + width)} cm", C),
        ],
    )


def _area(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    length, width = _sides(rng, difficulty)
    return _Draft(
        f"Quelle est l'aire d'un rectangle de {length} cm de long et {width} cm de large ?",
        f"{fmt(length * width)} cm²",
        [
            (f"{fmt(2 * (length + width))} cm²", ErrorType.CONFUSION),
            (f"{fmt(length + width)} cm²", M),
            (f"{fmt(length * width + length)} cm²", C),
        ],
    )


def _priority(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    a, b, c = rng.randint(2, 20), rng.randint(2, 9), rng.randint(2, 9)
    if difficulty == 3:
        d = rng.randint(2, 9)
        answer = a * b - c * d
        if answer <= 0:
            a = c * d + rng.randint(1, 9)
            answer = a * b - c * d
        return _Draft(
            f"Combien font {a} × {b} − {c} × {d} ?",
            fmt(answer),
            [
                (fmt((a * b - c) * d), M),
                (fmt(a * (b - c) * d), M),
                (fmt(answer + 1), C),
                (fmt(answer - 1), C),
            ],
        )
    return _Draft(
        f"Combien font {a} + {b} × {c} ?",
        fmt(a + b * c),
        [(fmt((a + b) * c), M), (fmt(a * b + c), M), (fmt(a + b + c), M), (fmt(a + b * c + 1), C)],
    )


def _power(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    base = rng.randint(2, 5 if difficulty < 3 else 10)
    exponent = rng.randint(2, 3 if difficulty == 1 else 4)
    answer = base**exponent
    return _Draft(
        f"Combien vaut {base}^{exponent} ?",
        fmt(answer),
        [
            (fmt(base * exponent), ErrorType.CONFUSION),
            (fmt(exponent**base), M),
            (fmt(base ** (exponent - 1)), C),
            (fmt(answer + base), C),
        ],
    )


def _equation(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    x = rng.randint(1, 12 if difficulty < 3 else 30)
    a = 1 if difficulty == 1 else rng.randint(2, 9)
    b = rng.randint(1, 20)
    c = a * x + b
    left = f"x + {b}" if a == 1 else f"{a}x + {b}"
    return _Draft(
        f"Quelle est la solution de l'équation {left} = {c} ?",
        f"x = {x}",
        [
            (f"x = {c + b}", M),  # « + b » passé de l'autre côté sans changer de signe
            (f"x = {c - b}", M) if a > 1 else (f"x = {c}", R),  # oublié de diviser par a
            (f"x = {x + 1}", C),
            (f"x = {x + 2}", C),
        ],
    )


_TRIPLES = ((3, 4, 5), (6, 8, 10), (5, 12, 13), (8, 15, 17), (9, 12, 15), (12, 16, 20), (7, 24, 25))


def _pythagore(rng: random.Random, grade: Grade, difficulty: int) -> _Draft:
    a, b, c = rng.choice(_TRIPLES[:2] if difficulty == 1 else _TRIPLES)
    if difficulty == 3:
        return _Draft(
            f"Un triangle ABC est rectangle en B, avec AC = {c} cm et AB = {a} cm. Combien mesure BC ?",
            f"{b} cm",
            [(f"{c - a} cm", M), (f"{c + a} cm", M), (f"{fmt(round(math.sqrt(c * c + a * a), 1))} cm", M)],
        )
    return _Draft(
        f"Un triangle ABC est rectangle en B, avec AB = {a} cm et BC = {b} cm. Combien mesure AC ?",
        f"{c} cm",
        [(f"{a + b} cm", M), (f"{a * a + b * b} cm", ErrorType.FORGOTTEN), (f"{c + 1} cm", C)],
    )


MAKERS: dict[Topic, Maker] = {
    Topic.ADD: _add,
    Topic.SUB: _sub,
    Topic.MUL: _mul,
    Topic.DIV: _div,
    Topic.DOUBLE: _double,
    Topic.PLACE: _place,
    Topic.COMPARE: _compare,
    Topic.FRACTION: _fraction,
    Topic.DECIMAL: _decimal,
    Topic.PERCENT: _percent,
    Topic.PROPORTION: _proportion,
    Topic.PERIMETER: _perimeter,
    Topic.AREA: _area,
    Topic.PRIORITY: _priority,
    Topic.POWER: _power,
    Topic.EQUATION: _equation,
    Topic.PYTHAGORE: _pythagore,
}


def _drafts(topic: Topic, rng: random.Random, grade: Grade, difficulty: int) -> Iterator[MaterialQuestion]:
    for _ in range(PER_DIFFICULTY * 4):  # quelques essais de plus : un tirage peut être écarté
        draft = MAKERS[topic](rng, grade, difficulty)
        if draft is not None and (question := _question(draft, difficulty)) is not None:
            yield question


def generated_questions(
    item: KnowledgeItem, grade: Grade, existing: Collection[str] = ()
) -> list[MaterialQuestion]:
    """Les questions créées pour la notion (vide si elle ne parle pas de calcul) ; aucune n'a
    l'énoncé d'une question existante."""
    rng = random.Random(f"{item.id}:{normalize(item.label)}:{grade.value}")
    seen = set(existing)
    found: list[MaterialQuestion] = []
    for topic in topics(item, grade):
        if topic not in MAKERS:
            continue  # l'heure et la monnaie se travaillent par des jeux dessinés, pas par QCM
        for difficulty in (1, 2, 3):
            kept = 0
            for question in _drafts(topic, rng, grade, difficulty):
                if question.stem in seen:
                    continue
                seen.add(question.stem)
                found.append(question)
                kept += 1
                if kept == PER_DIFFICULTY:
                    break
    return found


# Question de français glissée dans une leçon de maths (« Quelle est la bonne orthographe de
# numérateur ? ») : une leçon de maths ne fait réviser que les maths (règles 1.11.0).
_SPELLING = re.compile(r"orthograph|bien ecrit|correctement ecrit|comment s ecrit|s ecrit")


def math_only(material: KnowledgeMaterial) -> KnowledgeMaterial:
    """Le matériel d'une notion de maths sans exercice d'orthographe."""
    questions = [q for q in material.questions if not _SPELLING.search(normalize(q.stem))]
    if len(questions) == len(material.questions) and material.spelling is None:
        return material
    return material.model_copy(update={"questions": questions, "spelling": None})
