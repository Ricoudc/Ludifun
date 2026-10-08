"""Mode devoirs (cahier des charges §29, §127) : aider l'enfant à résoudre son exercice sans le
faire à sa place.

L'IA propose, à partir de l'énoncé : ce qu'on cherche, des étapes (indice, question
intermédiaire, rappel de notion, méthode), la réponse attendue, une solution détaillée et une
phrase pour vérifier. Le code décide :

- l'ordre des étapes, toujours celui du §127 : question → indice → question intermédiaire →
  rappel de notion → méthode → tentative de l'enfant → correction guidée ;
- les étapes gardées : une étape qui donnerait la réponse est retirée ;
- si la tentative est juste (règles d'équivalence de `app.domain.equivalence`, sans IA) ;
- quand la solution peut être montrée : jamais avant que l'enfant ait essayé, et pour un
  exercice à réponse courte, seulement après plusieurs tentatives et toutes les étapes vues.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.domain.equivalence import decimal_value, french_number, written_match
from app.domain.help import reveals
from app.domain.rules import RULES
from app.domain.text import normalize, strip_markup

ATTEMPTS_BEFORE_SOLUTION = RULES.homework.attempts_before_solution
MAX_STEPS = 6
MIN_STEPS = 2
STEP_MAX_LENGTH = 300
TASK_MAX_LENGTH = 200
SOLUTION_LINES = 6
STATEMENT_MAX_LENGTH = 3000


class StepKind(StrEnum):
    TASK = "task"  # Qu'est-ce qu'on cherche ?
    HINT = "hint"  # un indice
    QUESTION = "question"  # une question intermédiaire
    REMINDER = "reminder"  # rappel de la notion
    METHOD = "method"  # la méthode


ORDER = (StepKind.TASK, StepKind.HINT, StepKind.QUESTION, StepKind.REMINDER, StepKind.METHOD)
TITLES = {
    StepKind.TASK: "🔎 Qu'est-ce qu'on cherche ?",
    StepKind.HINT: "💡 Un indice",
    StepKind.QUESTION: "🤔 Une question pour avancer",
    StepKind.REMINDER: "📖 Rappel de la leçon",
    StepKind.METHOD: "🧭 La méthode",
}


class AnswerKind(StrEnum):
    NUMBER = "number"  # un nombre (avec ou sans unité) : vérifié par le code
    SHORT = "short"  # un mot, une courte expression : vérifiée par le code
    OPEN = "open"  # une phrase à rédiger : l'enfant compare avec la correction


@dataclass(frozen=True)
class Step:
    kind: StepKind
    text: str

    @property
    def title(self) -> str:
        return TITLES[self.kind]


@dataclass(frozen=True)
class HomeworkPlan:
    task: str  # ce qu'on cherche, redit simplement
    steps: tuple[Step, ...]
    answer: str  # jamais montrée avant la correction guidée
    answer_kind: AnswerKind
    solution: tuple[str, ...]  # correction guidée, ligne par ligne
    check: str  # comment vérifier son résultat

    def to_json(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "steps": [{"kind": s.kind.value, "text": s.text} for s in self.steps],
            "answer": self.answer,
            "answer_kind": self.answer_kind.value,
            "solution": list(self.solution),
            "check": self.check,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "HomeworkPlan":
        return cls(
            task=data["task"],
            steps=tuple(Step(StepKind(s["kind"]), s["text"]) for s in data["steps"]),
            answer=data["answer"],
            answer_kind=AnswerKind(data["answer_kind"]),
            solution=tuple(data["solution"]),
            check=data["check"],
        )


def _clean(text: Any, limit: int) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(strip_markup(text).split())
    return cleaned if cleaned and len(cleaned) <= limit else None


def check_plan(raw: dict[str, Any]) -> tuple[HomeworkPlan | None, list[str]]:
    """Le plan proposé par l'IA, remis dans l'ordre du §127 et sans ce qui donnerait la réponse ;
    `None` si on ne peut pas guider l'enfant sans la lui donner. Renvoie aussi ce qui a été écarté."""
    rejected: list[str] = []
    answer = _clean(raw.get("answer"), STEP_MAX_LENGTH)
    task = _clean(raw.get("task"), TASK_MAX_LENGTH)
    try:
        kind = AnswerKind(str(raw.get("answer_kind")))
    except ValueError:
        kind = AnswerKind.SHORT
    if answer is None or task is None:
        return None, ["réponse ou objectif absent ou trop long"]
    if kind is AnswerKind.NUMBER and not re.search(r"\d", answer):
        kind = AnswerKind.SHORT  # « Paul en a le plus » : pas un nombre
    hidden = kind is not AnswerKind.OPEN  # une réponse rédigée ne se « devine » pas mot à mot
    if hidden and reveals(task, answer):
        return None, ["l'objectif donne la réponse"]

    by_kind: dict[StepKind, list[str]] = {k: [] for k in ORDER}
    for i, raw_step in enumerate(raw.get("steps") or []):
        if not isinstance(raw_step, dict):
            continue
        text = _clean(raw_step.get("text"), STEP_MAX_LENGTH)
        try:
            step_kind = StepKind(str(raw_step.get("kind")))
        except ValueError:
            rejected.append(f"étape {i + 1} : type inconnu")
            continue
        if text is None:
            rejected.append(f"étape {i + 1} : vide ou trop longue")
        elif hidden and reveals(text, answer):
            rejected.append(f"étape {i + 1} : elle donnerait la réponse")
        elif text in by_kind[step_kind]:
            rejected.append(f"étape {i + 1} : en double")
        else:
            by_kind[step_kind].append(text)
    # L'objectif ouvre toujours la marche ; puis chaque type d'étape dans l'ordre du §127.
    steps = [Step(StepKind.TASK, task)] + [
        Step(k, text) for k in ORDER if k is not StepKind.TASK for text in by_kind[k]
    ]
    steps = steps[:MAX_STEPS]
    if len(steps) < MIN_STEPS:
        return None, [*rejected, "pas assez d'étapes sans donner la réponse"]
    solution = tuple(
        line for line in (_clean(s, STEP_MAX_LENGTH) for s in raw.get("solution") or []) if line
    )[:SOLUTION_LINES]
    check = _clean(raw.get("check"), STEP_MAX_LENGTH) or "Relis la question : ta réponse y répond-elle ?"
    return HomeworkPlan(task, tuple(steps), answer, kind, solution or (answer,), check), rejected


def _numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:[   ]\d{3})*(?:[.,]\d+)?", text)


def _last_number_in_words(text: str) -> int | None:
    """« Il reste huit billes » → 8 : la dernière suite de mots-nombres de la phrase."""
    run: list[str] = []
    found: int | None = None
    for word in [*re.split(r"[\s-]+", normalize(text)), ""]:
        if (word and french_number(word) is not None) or (run and word == "et"):
            run.append(word)
            continue
        if run and (value := french_number(" ".join(run))) is not None:
            found = value
        run = []
    return found


def judge(plan: HomeworkPlan, given: str, statement: str = "") -> bool | None:
    """La tentative est-elle juste ? `None` pour une réponse rédigée (l'enfant compare)."""
    if plan.answer_kind is AnswerKind.OPEN:
        return None
    # Un mot ou une expression : l'orthographe exacte, accents compris (« mangé » n'est pas
    # « manger ») ; c'est souvent ce que l'exercice fait travailler.
    exact = plan.answer_kind is AnswerKind.SHORT
    if written_match(given, plan.answer, exact_spelling=exact, context=statement):
        return True
    if plan.answer_kind is AnswerKind.NUMBER:
        # « Il reste 8 billes », « 24 - 16 = 8 » : le résultat est le dernier nombre écrit.
        expected, written = _numbers(plan.answer), _numbers(given)
        if expected and written:
            value = decimal_value(written[-1])
            return value is not None and value == decimal_value(expected[0])
        if expected and (in_words := _last_number_in_words(given)) is not None:
            return decimal_value(expected[0]) == in_words
    return False


@dataclass(frozen=True)
class AttemptRecord:
    text: str
    correct: bool | None


def solution_available(plan: HomeworkPlan, steps_shown: int, attempts: Sequence[AttemptRecord]) -> bool:
    """La correction guidée : après une tentative pour une réponse rédigée ; sinon après
    `ATTEMPTS_BEFORE_SOLUTION` tentatives fausses et toutes les étapes vues. Jamais d'emblée."""
    if not attempts:
        return False
    if plan.answer_kind is AnswerKind.OPEN:
        return True
    wrong = sum(1 for a in attempts if a.correct is False)
    return wrong >= ATTEMPTS_BEFORE_SOLUTION and steps_shown >= len(plan.steps)


def homework_input(statement: str, grade: str) -> str:
    """L'énoncé est une donnée, entre balises : s'il contient des consignes, elles ne sont pas
    suivies (§142-143)."""
    safe = statement.replace("<", "‹").replace(">", "›")
    return f"Classe de l'élève : {grade}\n\n<enonce>\n{safe}\n</enonce>"
