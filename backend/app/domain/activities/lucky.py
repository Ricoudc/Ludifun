"""Jeux de hasard sur plusieurs notions : la chance choisit la question, la leçon la fournit.

- « Roue aléatoire » (WHEEL) : la roue tourne trois fois ; chaque fois, elle s'arrête sur une
  case qui cache une question (QCM, sinon vrai ou faux) d'une notion différente.
- « Ouvrir la boîte » (BOX) : des boîtes numérotées ; chacune cache une question d'une notion.
- « Cartes aléatoires » (RANDOM_CARDS) : un paquet de cartes mémoire de plusieurs notions, tirées
  au hasard ; l'enfant retourne chaque carte et dit s'il savait (auto-évaluation).

Le hasard est tiré par le serveur (graine de la séance) : la roue s'arrête là où il l'a décidé, ce
qui permet de rejouer la séance à l'identique. Les cases et les boîtes ne portent pas le nom de la
notion, qui donnerait parfois la réponse.
"""

import random
from typing import Any

from pydantic import BaseModel, Field

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    parse_response,
)
from app.domain.activities.flashcard import Flashcard
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit

CHOICE_IDS = ("a", "b", "c", "d")
SEGMENTS = ("🍎", "🚀", "⭐", "🎈", "🐱", "🌈")  # cases de la roue
SPINS = 3


class _Answer(BaseModel):
    id: str
    choice_id: str


class QuestionsResponse(ResponseModel):
    answers: list[_Answer] = Field(max_length=len(SEGMENTS))


def _question(unit: KnowledgeUnit, rng: random.Random) -> tuple[dict[str, Any], str, str]:
    """Une question de la notion (QCM le plus facile, sinon vrai ou faux) : charge utile, identifiant
    de la bonne réponse, bonne réponse lisible."""
    material = unit.material
    if material.questions:
        easiest = min(q.difficulty for q in material.questions)
        question = rng.choice([q for q in material.questions if q.difficulty == easiest])
        texts = [question.answer, *question.distractors]
        rng.shuffle(texts)
        choices = [{"id": c, "text": t} for c, t in zip(CHOICE_IDS, texts, strict=True)]
        payload: dict[str, Any] = {"prompt": question.stem, "choices": choices}
        if question.passage:
            payload["passage"] = question.passage
        if question.source is not None:
            payload["source"] = question.source.site  # question d'un site de confiance (§117)
        return payload, CHOICE_IDS[texts.index(question.answer)], question.answer
    statements = [(s, True) for s in material.true_statements] + [
        (s, False) for s in material.false_statements
    ]
    text, value = rng.choice(statements)
    payload = {
        "prompt": f"Vrai ou faux ? {text}",
        "choices": [{"id": "a", "text": "Vrai"}, {"id": "b", "text": "Faux"}],
    }
    return payload, "a" if value else "b", "Vrai" if value else "Faux"


class _QuestionGame(ActivityType):
    """Plusieurs questions, une par notion, révélées par un jeu de hasard."""

    knowledge_types = ALL_TYPES
    difficulties = frozenset({1})
    multi_knowledge = True

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        m = unit.material
        return bool(m.questions or m.true_statements or m.false_statements)

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return len({u.id for u in units}) == len(units)

    def _questions(
        self, units: list[KnowledgeUnit], rng: random.Random
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        questions, expected, knowledge_by_question, displays, prompts = [], {}, {}, {}, {}
        for index, unit in enumerate(units, start=1):
            payload, answer_id, display = _question(unit, rng)
            question_id = f"q{index}"
            questions.append({"id": question_id, **payload})
            expected[question_id] = answer_id
            knowledge_by_question[question_id] = unit.id
            displays[question_id] = display
            prompts[question_id] = payload["prompt"]
        solution = {
            "expected": expected,
            "knowledge_by_question": knowledge_by_question,
            "displays": displays,
            "prompts": prompts,
            "display": " ; ".join(displays.values()),
        }
        return questions, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(QuestionsResponse, response).answers
        expected: dict[str, str] = activity.solution["expected"]
        ids = [a.id for a in given]
        if len(set(ids)) != len(ids) or not set(ids) <= set(expected):
            raise InvalidResponse("question inconnue ou répondue deux fois")
        answers = {a.id: a.choice_id for a in given}
        evidence: dict[str, float] = {}
        details = []
        for question_id, answer_id in expected.items():
            correct = answers.get(question_id) == answer_id
            evidence[activity.solution["knowledge_by_question"][question_id]] = 1.0 if correct else 0.0
            details.append(
                {
                    "id": question_id,
                    "text": activity.solution["prompts"][question_id],
                    "correct": correct,
                    "expected": activity.solution["displays"][question_id],
                }
            )
        good = sum(1 for d in details if d["correct"])
        return Grade(
            score=good / len(expected),
            evidence=evidence,
            errors={k: ErrorType.KNOWLEDGE for k, result in evidence.items() if result < 1},
            correct_answer=f"{good} bonne(s) réponse(s) sur {len(expected)}",
            details=details,
        )


class Wheel(_QuestionGame):
    code = ActivityCode.WHEEL
    base_duration_s = 60
    min_units = SPINS
    max_units = len(SEGMENTS)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        segments = [{"id": f"s{i}", "text": SEGMENTS[i]} for i in range(len(units))]
        stops = rng.sample(range(len(units)), SPINS)  # trois cases différentes
        chosen = [units[i] for i in stops]
        questions, solution = self._questions(chosen, rng)
        for question, stop in zip(questions, stops, strict=True):
            question["segment"] = segments[stop]["id"]
        payload = {
            "prompt": "Fais tourner la roue, puis réponds à la question.",
            "segments": segments,
            "spins": questions,
        }
        return payload, solution


class Box(_QuestionGame):
    code = ActivityCode.BOX
    base_duration_s = 70
    min_units = 4
    max_units = len(SEGMENTS)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        shuffled = list(units)
        rng.shuffle(shuffled)
        questions, solution = self._questions(shuffled, rng)
        for number, question in enumerate(questions, start=1):
            question["number"] = number
        payload = {"prompt": "Ouvre chaque boîte et réponds à la question cachée.", "boxes": questions}
        return payload, solution


class _Card(BaseModel):
    id: str
    knew: bool


class RandomCardsResponse(ResponseModel):
    cards: list[_Card] = Field(max_length=len(SEGMENTS))


class RandomCards(ActivityType):
    code = ActivityCode.RANDOM_CARDS
    knowledge_types = Flashcard.knowledge_types
    difficulties = frozenset({2})
    base_duration_s = 50
    evidence_factor = 0.5  # auto-évaluation, comme la carte mémoire
    multi_knowledge = True
    min_units = 3
    max_units = len(SEGMENTS)

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.flashcard is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return len({u.id for u in units}) == len(units)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deck = list(units)
        rng.shuffle(deck)
        cards, knowledge_by_card, backs, fronts = [], {}, {}, {}
        for index, unit in enumerate(deck, start=1):
            card = unit.material.flashcard
            assert card is not None
            card_id = f"c{index}"
            cards.append({"id": card_id, "front": card.front, "back": card.back})
            knowledge_by_card[card_id] = unit.id
            backs[card_id] = card.back
            fronts[card_id] = card.front
        payload = {"prompt": "Tire une carte, essaie de répondre, puis retourne-la.", "cards": cards}
        return payload, {
            "knowledge_by_card": knowledge_by_card,
            "backs": backs,
            "fronts": fronts,
            "display": " ; ".join(f"{fronts[c]} : {backs[c]}" for c in backs),
        }

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(RandomCardsResponse, response).cards
        knowledge_by_card: dict[str, str] = activity.solution["knowledge_by_card"]
        ids = [c.id for c in given]
        if len(set(ids)) != len(ids) or not set(ids) <= set(knowledge_by_card):
            raise InvalidResponse("carte inconnue ou notée deux fois")
        knew = {c.id: c.knew for c in given}
        evidence = {knowledge_by_card[c]: 1.0 if knew.get(c) else 0.0 for c in knowledge_by_card}
        details = [
            {
                "id": c,
                "text": activity.solution["fronts"][c],
                "correct": bool(knew.get(c)),
                "expected": activity.solution["backs"][c],
            }
            for c in knowledge_by_card
        ]
        good = sum(1 for d in details if d["correct"])
        return Grade(
            score=good / len(details),
            evidence=evidence,
            errors={k: ErrorType.FORGOTTEN for k, result in evidence.items() if result < 1},
            correct_answer=f"{good} carte(s) sue(s) sur {len(details)}",
            details=details,
        )
