"""Jeux de maths fabriqués et corrigés par le code, à la classe de l'enfant : aucune IA, la bonne
réponse est calculée. Ils sont proposés pour une notion de maths dont le thème s'y prête
(`app.domain.math_generator.topics`).

- « Droite graduée » (NUMBER_LINE) : toucher la graduation d'un nombre, ou lire le nombre que
  montre la flèche ; entiers, décimaux ou fractions selon la notion.
- « Fraction à colorier » (FRACTION_BAR) : colorier les 3/5 d'une bande ou d'un disque, lire la
  fraction coloriée, colorier une fraction égale (les 1/2 d'une bande en 6 parts).
- « Opération posée » (COLUMN_OP) : addition, soustraction ou multiplication posée ; une erreur
  de retenue est reconnue et dite au parent.
"""

import random
import re
from fractions import Fraction
from typing import Any

from pydantic import Field

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.errors import ErrorType
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeType, KnowledgeUnit, Subject
from app.domain.math_generator import Topic, fmt, topics

GRADES = list(SchoolGrade)
DEFAULT_GRADE = SchoolGrade.CM1


def _grade_of(unit: KnowledgeUnit) -> SchoolGrade:
    return unit.grade or DEFAULT_GRADE


def _rank(grade: SchoolGrade) -> int:
    return GRADES.index(grade)


def _topics(unit: KnowledgeUnit) -> set[Topic]:
    if unit.subject != Subject.MATH:
        return set()
    return set(topics(unit.item, _grade_of(unit)))


def _choices(answer: str, wrong: list[str], rng: random.Random) -> tuple[list[dict[str, str]], str] | None:
    """Quatre choix mélangés (la réponse et trois erreurs différentes), et l'identifiant juste."""
    others = list(dict.fromkeys(w for w in wrong if w != answer and not w.startswith("-")))[:3]
    if len(others) < 3:
        return None
    texts = [answer, *others]
    rng.shuffle(texts)
    ids = ("a", "b", "c", "d")
    return [{"id": i, "text": t} for i, t in zip(ids, texts, strict=True)], ids[texts.index(answer)]


class ChoiceResponse(ResponseModel):
    choice_id: str


def _grade_choice(activity: BuiltActivity, response: dict[str, Any]) -> tuple[float, ErrorType | None]:
    choice = parse_response(ChoiceResponse, response).choice_id
    if choice not in {c["id"] for c in activity.payload["choices"]}:
        raise InvalidResponse(f"choix inconnu : {choice}")
    if choice == activity.solution["choice_id"]:
        return 1.0, None
    kind = activity.solution.get("misconceptions", {}).get(choice)
    return 0.0, ErrorType(kind) if kind in ErrorType else ErrorType.METHOD


def _result(
    activity: BuiltActivity, score: float, error: ErrorType | None, explanation: str | None = None
) -> Grade:
    knowledge_id, solution = activity.knowledge_ids[0], activity.solution
    return Grade(
        score=score,
        evidence={knowledge_id: score},
        errors={knowledge_id: error or ErrorType.CALCULATION} if score < 1 else {},
        correct_answer=solution["display"],
        tip=solution.get("tip"),
        explanation=explanation or solution.get("explanation"),
    )


# --------------------------------------------------------------------------- #
# Droite graduée
# --------------------------------------------------------------------------- #

NUMBER_TOPICS = {
    Topic.COMPARE,
    Topic.PLACE,
    Topic.ADD,
    Topic.SUB,
    Topic.DOUBLE,
    Topic.FRACTION,
    Topic.DECIMAL,
}
INTEGER_STEPS = {
    SchoolGrade.CP: (1, 1, 2),
    SchoolGrade.CE1: (1, 2, 5),
    SchoolGrade.CE2: (1, 5, 10),
    SchoolGrade.CM1: (10, 50, 100),
}


_YEAR = re.compile(r"(?<![\d,.])(\d{3,4})(?![\d,.])")


def _year(unit: KnowledgeUnit) -> int | None:
    """L'année d'une date ou d'un événement d'histoire (« 1789 », « en 800 »), hors maths."""
    if unit.subject == Subject.MATH or unit.type not in (KnowledgeType.DATE, KnowledgeType.EVENT):
        return None
    attributes = unit.item.attributes
    text = str(attributes.get("value") or attributes.get("date") or "")
    if re.search(r"av(\.|ant) ?j", text.lower()):
        return None  # avant Jésus-Christ : une autre frise
    found = _YEAR.search(text)
    year = int(found.group(1)) if found else None
    return year if year is not None and 100 <= year <= 2100 else None


def _event(unit: KnowledgeUnit) -> str:
    event = unit.item.attributes.get("event") if unit.type == KnowledgeType.DATE else None
    return str(event or unit.item.label)


class IndexResponse(ResponseModel):
    index: int = Field(ge=0, le=40)


def _fraction_text(value: Fraction, denominator: int) -> str:
    """« 3/4 » sur une droite partagée en quarts (pas simplifiée : c'est ce que montre la droite)."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value * denominator}/{denominator}"


class NumberLine(ActivityType):
    code = ActivityCode.NUMBER_LINE
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 20

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_topics(unit) & NUMBER_TOPICS) or _year(unit) is not None

    @staticmethod
    def _frise(
        unit: KnowledgeUnit, year: int, difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Histoire : placer une date sur une frise. Difficulté 1, frise d'un siècle graduée tous
        les 10 ans ; 2, frise de 10 ans graduée année par année ; 3, comme 1 mais sans donner
        l'année (il faut la savoir). Entre deux graduations, la plus proche est juste (les deux
        pour une année en 5)."""
        event = _event(unit)
        if difficulty == 2:
            start = year - year % 10 if year % 10 else year - 5  # une frise de 1780 à 1790
            step, accepted = 1, [year - start]
        else:
            start, step = year // 100 * 100, 10
            offset = year - start
            accepted = sorted(
                {offset // 10, (offset + 9) // 10} if offset % 10 == 5 else {round(offset / 10)}
            )
        labeled = [0, 10] if difficulty == 2 else [0, 5, 10]
        payload = {
            "prompt": (
                f"Place « {event} » sur la frise."
                if difficulty == 3
                else f"Place l'année {year} sur la frise."
                if difficulty == 2 or year % 10 == 0
                else f"Touche la graduation la plus proche de l'année {year}."
            ),
            "task": "place",
            "intervals": 10,
            "labels": [{"index": i, "text": str(start + step * i)} for i in labeled],
        }
        return payload, {
            "index": accepted[0],
            "accepted": accepted,
            "display": f"{event}, en {year}.",
            **feedback(unit),
        }

    @staticmethod
    def _line(unit: KnowledgeUnit, difficulty: int, rng: random.Random) -> dict[str, Any]:
        """La droite : origine, pas, nombre d'intervalles, graduations écrites, nombre visé."""
        kind = _topics(unit)
        grade = _grade_of(unit)
        if Topic.FRACTION in kind:
            denominator = rng.choice((2, 4) if difficulty == 1 else (3, 4, 5, 6, 8, 10))
            intervals = denominator * (2 if difficulty == 3 else 1)
            step, start = Fraction(1, denominator), Fraction(0)
            labeled = sorted({0, denominator, intervals})

            def text(i: int) -> str:
                return _fraction_text(start + step * i, denominator)

            step_text = f"1/{denominator}"
        elif Topic.DECIMAL in kind:
            if difficulty == 3:
                step = Fraction(1, 100)
                start = Fraction(rng.randint(1, 9)) + Fraction(rng.randint(0, 9), 10)
            else:
                step, start = Fraction(1, 10), Fraction(rng.randint(0, 9))
            intervals, labeled = 10, [0, 10]

            def text(i: int) -> str:
                return fmt(start + step * i)

            step_text = fmt(step)
        else:
            steps = INTEGER_STEPS.get(grade, (100, 500, 1000))
            step = Fraction(steps[difficulty - 1])
            start = step * 10 * rng.randint(0, 4 if grade == SchoolGrade.CP else 9)
            intervals = 10
            labeled = [0, 5, 10] if difficulty == 1 else [0, 10]

            def text(i: int) -> str:
                return fmt(start + step * i)

            step_text = fmt(step)
        target = rng.choice([i for i in range(1, intervals) if i not in labeled])
        return {
            "intervals": intervals,
            "labels": [{"index": i, "text": text(i)} for i in labeled],
            "target": target,
            "value": text(target),
            "text": text,
            "step": step_text,
        }

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        year = _year(unit)
        if year is not None and not _topics(unit) & NUMBER_TOPICS:
            return self._frise(unit, year, difficulty, rng)
        for _ in range(20):
            line = self._line(unit, difficulty, rng)
            target, text = line["target"], line["text"]
            display = (
                f"{line['value']} est {target} graduation{'s' if target > 1 else ''} après {text(0)}. "
                f"Chaque graduation vaut {line['step']}."
            )
            base = {"intervals": line["intervals"], "labels": line["labels"]}
            if difficulty != 2:
                payload = {
                    "prompt": f"Touche la graduation du nombre {line['value']}.",
                    "task": "place",
                    **base,
                }
                return payload, {"index": target, "display": display, **feedback(unit)}
            wrong = [
                (text(target + 1), ErrorType.CALCULATION),
                (text(target - 1), ErrorType.CALCULATION),
                (text(min(line["intervals"], target + 2)), ErrorType.CALCULATION),
                (text(line["intervals"] - target), ErrorType.READING),
            ]
            choices = _choices(line["value"], [w for w, _ in wrong], rng)
            if choices is None:
                continue
            listed, answer_id = choices
            kinds = {w: k.value for w, k in wrong}
            payload = {
                "prompt": "Quel nombre montre la flèche ?",
                "task": "read",
                "arrow": target,
                "choices": listed,
                **base,
            }
            misconceptions = {c["id"]: kinds[c["text"]] for c in listed if c["id"] != answer_id}
            return payload, {
                "choice_id": answer_id,
                "misconceptions": misconceptions,
                "display": display,
                **feedback(unit),
            }
        raise ValueError("droite impossible")  # pragma: no cover

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        if activity.payload["task"] == "read":
            score, error = _grade_choice(activity, response)
            return _result(activity, score, error)
        index = parse_response(IndexResponse, response).index
        if index > activity.payload["intervals"]:
            raise InvalidResponse("graduation hors de la droite")
        expected = activity.solution["index"]
        accepted = activity.solution.get("accepted", [expected])
        error = ErrorType.CALCULATION if abs(index - expected) == 1 else ErrorType.METHOD
        if "accepted" in activity.solution:
            error = ErrorType.KNOWLEDGE  # une frise d'histoire : la date n'est pas encore sue
        return _result(activity, 1.0 if index in accepted else 0.0, error)


# --------------------------------------------------------------------------- #
# Fraction à colorier
# --------------------------------------------------------------------------- #


class ColoredResponse(ResponseModel):
    colored: list[int] = Field(max_length=24)


SHAPES = {"bar": "de la bande", "disc": "du disque"}


def _parts(count: int) -> str:
    return f"{count} part" if count == 1 else f"{count} parts"


class FractionBar(ActivityType):
    code = ActivityCode.FRACTION_BAR
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 20

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return Topic.FRACTION in _topics(unit)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        shape = rng.choice(tuple(SHAPES))
        of = SHAPES[shape]
        if difficulty == 2:
            for _ in range(20):
                parts = rng.randint(3, 10)
                count = rng.randint(1, parts - 1)
                answer = f"{count}/{parts}"
                wrong = {
                    f"{parts}/{count}": ErrorType.CONFUSION,  # numérateur et dénominateur inversés
                    f"{parts - count}/{parts}": ErrorType.READING,  # la part qui n'est pas coloriée
                    f"{count}/{parts - count}": ErrorType.METHOD,  # coloriées / pas coloriées
                    f"{count}/{parts + 1}": ErrorType.CALCULATION,
                }
                choices = _choices(answer, list(wrong), rng)
                if choices is None:
                    continue
                listed, answer_id = choices
                payload = {
                    "prompt": f"Quelle fraction {of} est coloriée ?",
                    "task": "read",
                    "shape": shape,
                    "parts": parts,
                    "colored": sorted(rng.sample(range(parts), count)),
                    "choices": listed,
                }
                return payload, {
                    "choice_id": answer_id,
                    "misconceptions": {
                        c["id"]: wrong[c["text"]].value for c in listed if c["id"] != answer_id
                    },
                    "display": f"{_parts(count)} sur {parts} en couleur, soit {answer} {of}.",
                    **feedback(unit),
                }
            raise ValueError("fraction impossible")  # pragma: no cover
        if difficulty == 1:
            parts = rng.randint(2, 8)
            count = rng.randint(1, parts - 1)
            fraction, display = f"{count}/{parts}", f"Il fallait colorier {_parts(count)} sur {parts}."
        else:  # une fraction égale : les 1/2 d'une bande partagée en 6
            simple = Fraction(rng.randint(1, 3), rng.randint(2, 5))
            while simple >= 1:
                simple = Fraction(rng.randint(1, 3), rng.randint(2, 5))
            factor = rng.choice((2, 3))
            parts, count = simple.denominator * factor, simple.numerator * factor
            fraction = f"{simple.numerator}/{simple.denominator}"
            display = f"Les {fraction} {of}, c'est {_parts(count)} sur {parts}."
        payload = {"prompt": f"Colorie les {fraction} {of}.", "task": "color", "shape": shape, "parts": parts}
        return payload, {"count": count, "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        if activity.payload["task"] == "read":
            score, error = _grade_choice(activity, response)
            return _result(activity, score, error)
        colored = set(parse_response(ColoredResponse, response).colored)
        parts, count = activity.payload["parts"], activity.solution["count"]
        if not colored <= set(range(parts)):
            raise InvalidResponse("part inconnue")
        # N'importe quelles parts conviennent : c'est leur nombre qui compte.
        error = ErrorType.READING if len(colored) == parts - count else ErrorType.METHOD
        return _result(activity, 1.0 if len(colored) == count else 0.0, error)


# --------------------------------------------------------------------------- #
# Opération posée
# --------------------------------------------------------------------------- #


class ResultResponse(ResponseModel):
    result: str = Field(max_length=12)


DIGITS = {SchoolGrade.CE1: 2, SchoolGrade.CE2: 3, SchoolGrade.CM1: 4}


def _digits(number: int) -> list[int]:
    return [int(d) for d in str(number)]


def without_carry(a: int, b: int, operator: str) -> int | None:
    """Le résultat d'un enfant qui oublie les retenues (colonne par colonne, sans rien reporter) :
    addition, chaque chiffre de la somme modulo 10 ; soustraction, « le petit ôté du grand »."""
    width = max(len(str(a)), len(str(b)))
    da, db = str(a).zfill(width), str(b).zfill(width)
    if operator == "+":
        column = [(int(x) + int(y)) % 10 for x, y in zip(da, db, strict=True)]
    elif operator == "−":
        column = [abs(int(x) - int(y)) for x, y in zip(da, db, strict=True)]
    else:
        return None
    return int("".join(map(str, column)))


class ColumnOperation(ActivityType):
    code = ActivityCode.COLUMN_OP
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 45

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return _rank(_grade_of(unit)) >= _rank(SchoolGrade.CE1) and bool(self._operators(unit))

    @staticmethod
    def _operators(unit: KnowledgeUnit) -> list[str]:
        found = _topics(unit)
        operators = [o for o, t in (("+", Topic.ADD), ("−", Topic.SUB)) if t in found]
        if Topic.MUL in found and _rank(_grade_of(unit)) >= _rank(SchoolGrade.CE2):
            operators.append("×")
        return operators

    @staticmethod
    def _numbers(operator: str, grade: SchoolGrade, difficulty: int, rng: random.Random) -> tuple[int, int]:
        width = DIGITS.get(grade, 5) + (1 if difficulty == 3 and grade != SchoolGrade.CE1 else 0)
        low, high = 10 ** (width - 1), 10**width - 1
        for _ in range(200):
            if operator == "×":
                if difficulty == 3 and _rank(grade) >= _rank(SchoolGrade.CM1):
                    a, b = rng.randint(12, 99), rng.randint(12, 99)
                else:
                    a, b = (
                        rng.randint(12 if difficulty == 1 else 102, 99 if difficulty == 1 else 999),
                        rng.randint(2, 9),
                    )
                return a, b
            a, b = rng.randint(low, high), rng.randint(low // 10 or 1, high)
            if operator == "−" and a < b:
                a, b = b, a
            if a == b:
                continue
            simple = without_carry(a, b, operator) == (a + b if operator == "+" else a - b)
            if (difficulty == 1) == simple:  # difficulté 1 : sans retenue ; ensuite : avec
                return a, b
        return a, b

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        operator = rng.choice(self._operators(unit))
        a, b = self._numbers(operator, _grade_of(unit), difficulty, rng)
        result = a + b if operator == "+" else a - b if operator == "−" else a * b
        boxes = (
            len(str(max(a, b))) + 1
            if operator == "+"
            else len(str(a))
            if operator == "−"
            else len(str(a * 9 if b < 10 else a * 99))
        )
        payload = {
            "prompt": f"Pose et calcule : {fmt(a)} {operator} {fmt(b)}",
            "operator": operator,
            "operands": [str(a), str(b)],
            "boxes": max(boxes, len(str(result))),
        }
        return payload, {
            "result": str(result),
            "carry_slip": without_carry(a, b, operator),
            "display": f"{fmt(a)} {operator} {fmt(b)} = {fmt(result)}",
            **feedback(unit),
        }

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        written = parse_response(ResultResponse, response).result.strip().lstrip("0") or "0"
        if not written.isdigit():
            raise InvalidResponse("un résultat s'écrit avec des chiffres")
        solution = activity.solution
        if written == solution["result"]:
            return _result(activity, 1.0, None)
        if solution.get("carry_slip") is not None and written == str(solution["carry_slip"]):
            hint = (
                "Attention aux retenues : quand une colonne dépasse 9, on écrit les unités et on "
                "retient la dizaine dans la colonne suivante."
                if activity.payload["operator"] == "+"
                else "Attention : quand le chiffre du haut est plus petit, on emprunte une dizaine."
            )
            return _result(activity, 0.0, ErrorType.METHOD, hint)
        return _result(activity, 0.0, ErrorType.CALCULATION)
