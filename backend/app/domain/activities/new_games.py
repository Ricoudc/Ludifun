"""Neuf jeux d'apprentissage de novembre 2026 (§5.98), fabriqués par le code à partir du matériel
déjà contrôlé de la leçon (aucun appel à l'IA) :

- « Chasse à l'erreur » (SPOT_ERROR) : une phrase vraie de la leçon où un mot a été remplacé par
  une mauvaise réponse connue ; toucher le mot faux, puis choisir la bonne correction ;
- « Phrase qui s'efface » (FADING) : la phrase à retenir, lue un moment, puis des mots cachés à
  retrouver (deux mots importants, puis la moitié des mots) ;
- « Le bon ordre » (STEP_ORDER) : les étapes de la méthode (aide « étapes ») mélangées à une
  étape fausse, à écarter ;
- « Le correcteur » (CHECK_LUDI) : Ludi a répondu à une question ; a-t-il raison, et sinon,
  pourquoi s'est-il trompé (le type d'erreur que révèle ce mauvais choix) ;
- « Qui suis-je ? » (WHO_AM_I) : trois indices, du plus vague au plus précis, pour retrouver une
  notion parmi d'autres de la leçon ;
- « L'escalier » (STAIRS) : les questions de la notion, de la plus facile à la plus difficile ;
- « Le train des mots » (WORD_TRAIN, CP-CE1) : le téléphone dit un mot, l'enfant accroche les
  wagons de ses syllabes dans l'ordre (mots découpés à la main) ;
- « Compte et touche » (COUNT_TOUCH, CP-CE1) : toucher autant d'objets que le nombre dit.

Aucun texte n'est inventé : tout vient du matériel validé (`validation.py`) ou des banques de
mots écrites à la main. Un jeu qui n'a pas ce qu'il lui faut n'est pas proposé (`_has_material`).
"""

import random
import re
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
from app.domain.activities.math_games import NUMBER_TOPICS, _topics
from app.domain.activities.word_games import _french
from app.domain.equivalence import same_answer
from app.domain.errors import ErrorType
from app.domain.french import SYLLABLE_WORDS, FrenchTopic
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeUnit, MaterialQuestion, Subject
from app.domain.text import normalize

YOUNG = frozenset({SchoolGrade.CP, SchoolGrade.CE1})


def _one(activity: BuiltActivity, score: float, error: ErrorType, display: str, **extra: Any) -> Grade:
    knowledge_id = activity.knowledge_ids[0]
    return Grade(
        score=score,
        evidence={knowledge_id: score},
        errors={knowledge_id: error} if score < 1 else {},
        correct_answer=display,
        tip=activity.solution.get("tip"),
        explanation=activity.solution.get("explanation"),
        details=extra.get("details", []),
    )


def _ids(prefix: str, texts: list[str]) -> list[dict[str, str]]:
    return [{"id": f"{prefix}{i}", "text": t} for i, t in enumerate(texts, start=1)]


# --------------------------------------------------------------------------- #
# Chasse à l'erreur
# --------------------------------------------------------------------------- #


def _span(sentence: str, answer: str) -> re.Match[str] | None:
    """La réponse, mot entier, dans la phrase (casse ignorée)."""
    if not answer.strip() or len(answer.split()) > 5:
        return None
    return re.search(rf"(?<!\w){re.escape(answer.strip())}(?!\w)", sentence, re.IGNORECASE)


def _spots(unit: KnowledgeUnit) -> list[tuple[str, MaterialQuestion, re.Match[str], list[str]]]:
    """(phrase vraie, question, place de la réponse dans la phrase, mauvaises réponses possibles)."""
    sentences = [*unit.material.true_statements, unit.item.statement]
    found = []
    for question in unit.material.questions:
        if question.source is not None or question.generated:
            continue
        wrong = [
            d
            for d in question.distractors
            if not same_answer(d, question.answer) and normalize(question.answer) not in normalize(d)
        ]
        if len(wrong) < 3:
            continue
        for sentence in sentences:
            if (match := _span(sentence, question.answer)) is not None:
                found.append((sentence, question, match, wrong))
                break
    return found


class SpotErrorResponse(ResponseModel):
    word_id: str = Field(max_length=10)
    choice_id: str | None = Field(None, max_length=10)


class SpotError(ActivityType):
    code = ActivityCode.SPOT_ERROR
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_spots(unit))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        sentence, question, match, wrong = rng.choice(_spots(unit))
        bad = rng.choice(wrong)
        before, after = sentence[: match.start()].split(), sentence[match.end() :].split()
        words = [*before, bad, *after]
        error_id = f"w{len(before) + 1}"
        options = [question.answer, *rng.sample([w for w in wrong if w != bad], 2)]
        rng.shuffle(options)
        choices = _ids("c", options)
        right = next(c["id"] for c in choices if c["text"] == question.answer)
        payload = {
            "prompt": "Une phrase de ta leçon contient une erreur.",
            "words": _ids("w", words),
            "choices": choices,
        }
        solution = {"error_id": error_id, "choice_id": right, "display": sentence, **feedback(unit)}
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(SpotErrorResponse, response)
        if given.word_id not in {w["id"] for w in activity.payload["words"]}:
            raise InvalidResponse("mot inconnu")
        found = given.word_id == activity.solution["error_id"]
        fixed = found and given.choice_id == activity.solution["choice_id"]
        score = 1.0 if fixed else 0.5 if found else 0.0
        return _one(activity, score, ErrorType.KNOWLEDGE, activity.solution["display"])


# --------------------------------------------------------------------------- #
# Phrase qui s'efface
# --------------------------------------------------------------------------- #

FADING_WORDS = (4, 18)
_EDGE = ".,;:!?…«»\"'()"


def _fading_words(unit: KnowledgeUnit) -> list[str]:
    return unit.item.statement.split()


def _bare(word: str) -> str:
    return normalize(word.strip(_EDGE))


class FadingResponse(ResponseModel):
    answers: list[tuple[int, str]] = Field(max_length=FADING_WORDS[1])


class FadingSentence(ActivityType):
    """Difficulté 2 : deux mots importants cachés ; 3 : la moitié des mots. Pas de difficulté 1 :
    une notion fragile se revoit d'abord avec la réponse sous les yeux (QCM, vrai ou faux)."""

    code = ActivityCode.FADING
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2, 3})
    base_duration_s = 35

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        words = _fading_words(unit)
        return FADING_WORDS[0] <= len(words) <= FADING_WORDS[1] and sum(len(_bare(w)) > 3 for w in words) >= 2

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        words = _fading_words(unit)
        candidates = [i for i, w in enumerate(words) if _bare(w)]
        meaningful = sorted((i for i in candidates if len(_bare(words[i])) > 3), key=lambda i: -len(words[i]))
        if difficulty == 2:
            hidden = meaningful[:2]
        else:
            hidden = sorted(rng.sample(candidates, max(3, len(candidates) // 2)))
        hidden = sorted(hidden)
        payload = {
            "prompt": "Lis bien la phrase. Elle va s'effacer : retrouve les mots qui manquent.",
            "words": words,
            "hidden": hidden,
            "memorize_s": min(12, 3 + len(words) // 2),
        }
        expected = {str(i): words[i].strip(_EDGE) for i in hidden}
        return payload, {"expected": expected, "display": unit.item.statement, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        answers = {str(i): text for i, text in parse_response(FadingResponse, response).answers}
        expected: dict[str, str] = activity.solution["expected"]
        if not set(answers) <= set(expected):
            raise InvalidResponse("mot qui n'était pas caché")
        details = [
            {
                "id": i,
                "expected": word,
                "given": answers.get(i, ""),
                "correct": _bare(answers.get(i, "")) == _bare(word),
            }
            for i, word in expected.items()
        ]
        right = sum(1 for d in details if d["correct"])
        score = round(right / len(details), 2)
        error = ErrorType.IMPRECISION if score >= 0.5 else ErrorType.FORGOTTEN
        return _one(activity, score, error, activity.solution["display"], details=details)


# --------------------------------------------------------------------------- #
# Le bon ordre (étapes de la méthode et une étape fausse)
# --------------------------------------------------------------------------- #

STEPS = (3, 6)


def _steps(unit: KnowledgeUnit) -> list[str]:
    help_ = unit.material.help
    return list(help_.steps) if help_ is not None and STEPS[0] <= len(help_.steps) <= STEPS[1] else []


class StepOrderResponse(ResponseModel):
    order: list[str] = Field(max_length=STEPS[1])
    intruder: str = Field(max_length=10)


class StepOrder(ActivityType):
    code = ActivityCode.STEP_ORDER
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 40

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_steps(unit)) and bool(unit.material.false_statements)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        steps = _steps(unit)
        intruder_text = rng.choice(unit.material.false_statements)
        items = _ids("s", [*steps, intruder_text])
        intruder = items[-1]["id"]
        order = [i["id"] for i in items[:-1]]
        shuffled = items[:]
        while [i["id"] for i in shuffled if i["id"] != intruder] == order:
            rng.shuffle(shuffled)
        payload = {
            "prompt": "Remets les étapes dans l'ordre. Une étape est fausse : mets-la de côté.",
            "items": shuffled,
        }
        display = " → ".join(steps) + f" (fausse : « {intruder_text} »)"
        return payload, {"order": order, "intruder": intruder, "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(StepOrderResponse, response)
        known = {i["id"] for i in activity.payload["items"]}
        if not set(given.order) | {given.intruder} <= known:
            raise InvalidResponse("étape inconnue")
        order: list[str] = activity.solution["order"]
        placed = [s for s in given.order if s != given.intruder]
        in_place = sum(1 for a, b in zip(placed, order, strict=False) if a == b)
        score = 0.5 * (given.intruder == activity.solution["intruder"]) + 0.5 * in_place / len(order)
        error = ErrorType.METHOD if score < 1 else ErrorType.KNOWLEDGE
        return _one(activity, round(score, 2), error, activity.solution["display"])


# --------------------------------------------------------------------------- #
# Le correcteur (Ludi s'est-il trompé, et pourquoi ?)
# --------------------------------------------------------------------------- #

REASONS: dict[ErrorType, str] = {
    ErrorType.CALCULATION: "Une erreur de calcul",
    ErrorType.METHOD: "Il s'est trompé de méthode",
    ErrorType.READING: "Il a mal lu la question",
    ErrorType.CONFUSION: "Il a confondu avec autre chose",
    ErrorType.IMPRECISION: "C'est presque juste, un détail est faux",
    ErrorType.KNOWLEDGE: "Il ne le savait pas",
}


def _traps(unit: KnowledgeUnit) -> list[tuple[MaterialQuestion, str, ErrorType]]:
    found = []
    for question in unit.material.questions:
        for distractor in question.distractors:
            kind = question.misconception_of(distractor)
            if kind in {k.value for k in REASONS}:
                found.append((question, distractor, ErrorType(kind)))
    return found


class CheckLudiResponse(ResponseModel):
    right: bool
    reason_id: str | None = Field(None, max_length=10)


class CheckLudi(ActivityType):
    code = ActivityCode.CHECK_LUDI
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_traps(unit))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        question, trap, kind = rng.choice(_traps(unit))
        ludi_right = rng.random() < 1 / 3
        others = rng.sample([k for k in REASONS if k is not kind], 2)
        reasons = [kind, *others]
        rng.shuffle(reasons)
        listed = [{"id": f"r{i}", "text": REASONS[k]} for i, k in enumerate(reasons, start=1)]
        payload = {
            "question": question.stem,
            "ludi_answer": question.answer if ludi_right else trap,
            "reasons": listed,
        }
        reason_id = None if ludi_right else listed[reasons.index(kind)]["id"]
        display = (
            f"Ludi avait raison : « {question.answer} »."
            if ludi_right
            else f"La bonne réponse est « {question.answer} ». Ludi : {REASONS[kind].lower()}."
        )
        return payload, {
            "ludi_right": ludi_right,
            "reason_id": reason_id,
            "display": display,
            **feedback(unit),
        }

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(CheckLudiResponse, response)
        solution = activity.solution
        if solution["ludi_right"]:
            score = 1.0 if given.right else 0.0
        else:
            score = 0.0 if given.right else 0.5 + 0.5 * (given.reason_id == solution["reason_id"])
        return _one(activity, score, ErrorType.KNOWLEDGE, solution["display"])


# --------------------------------------------------------------------------- #
# Qui suis-je ?
# --------------------------------------------------------------------------- #


def _masked(text: str, label: str) -> str:
    out = text
    for word in sorted({w for w in re.findall(r"\w+", label) if len(w) > 2}, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "…", out, flags=re.IGNORECASE)
    return out


def _clues(unit: KnowledgeUnit) -> list[str]:
    """Du plus vague au plus précis : l'astuce, l'explication, la phrase à retenir ; le nom de la
    notion y est caché, et un indice qui n'en dit plus rien d'utile est écarté."""
    material, label = unit.material, unit.item.label
    texts = [material.tip, material.explanation, unit.item.statement]
    clues: list[str] = []
    for text in texts:
        if not text:
            continue
        clue = _masked(text, label)
        if normalize(label) in normalize(clue) or len(normalize(clue).replace("…", "").split()) < 3:
            continue
        if all(normalize(clue) != normalize(c) for c in clues):
            clues.append(clue)
    return clues[:3]


class WhoAmIResponse(ResponseModel):
    choice_id: str = Field(max_length=10)
    clues_used: int = Field(ge=1, le=3)


class WhoAmI(ActivityType):
    code = ActivityCode.WHO_AM_I
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 30
    multi_knowledge = True
    min_units = 3
    max_units = 4

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return len(unit.item.label) <= 60

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        labels = {normalize(u.item.label) for u in units}
        return len(labels) == len(units) and len(_clues(units[0])) >= 2

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        target = units[0]  # la première notion est celle à deviner
        options = [u.item.label for u in units]
        rng.shuffle(options)
        choices = _ids("c", options)
        right = next(c["id"] for c in choices if c["text"] == target.item.label)
        payload = {
            "prompt": "Qui suis-je ? Moins tu demandes d'indices, mieux c'est.",
            "clues": _clues(target),
            "choices": choices,
        }
        return payload, {"choice_id": right, "display": target.item.label, **feedback(target)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(WhoAmIResponse, response)
        right = given.choice_id == activity.solution["choice_id"]
        target = activity.knowledge_ids[0]
        # Trouvé avec peu d'indices : la notion est sue ; avec tous : reconnue seulement.
        score = (1.0 if given.clues_used < 3 else 0.8) if right else 0.0
        return Grade(
            score=score,
            evidence={target: score},
            errors={} if right else {target: ErrorType.CONFUSION},
            correct_answer=activity.solution["display"],
            tip=activity.solution.get("tip"),
            explanation=activity.solution.get("explanation"),
        )


# --------------------------------------------------------------------------- #
# L'escalier
# --------------------------------------------------------------------------- #

STAIRS = (3, 5)


def _stairs(unit: KnowledgeUnit) -> list[MaterialQuestion]:
    questions = [q for q in unit.material.questions if q.source is None]
    if len({q.difficulty for q in questions}) < 2:
        return []
    return sorted(questions, key=lambda q: q.difficulty)


class StairsResponse(ResponseModel):
    answers: list[tuple[str, str]] = Field(max_length=STAIRS[1])


class Stairs(ActivityType):
    code = ActivityCode.STAIRS
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 60

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return len(_stairs(unit)) >= STAIRS[0]

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        available = _stairs(unit)
        picked = sorted(rng.sample(available, min(STAIRS[1], len(available))), key=lambda q: q.difficulty)
        steps, right = [], {}
        for n, question in enumerate(picked, start=1):
            options = [question.answer, *question.distractors]
            rng.shuffle(options)
            choices = _ids("c", options)
            steps.append({"id": f"m{n}", "prompt": question.stem, "choices": choices})
            right[f"m{n}"] = next(c["id"] for c in choices if c["text"] == question.answer)
        payload = {"prompt": "Monte l'escalier : chaque marche est un peu plus difficile.", "steps": steps}
        display = " ; ".join(q.answer for q in picked)
        return payload, {"right": right, "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        answers = dict(parse_response(StairsResponse, response).answers)
        right: dict[str, str] = activity.solution["right"]
        if not set(answers) <= set(right):
            raise InvalidResponse("marche inconnue")
        details = [{"id": step, "correct": answers.get(step) == choice} for step, choice in right.items()]
        reached = 0
        for detail in details:  # marches montées sans faute, depuis la première
            if not detail["correct"]:
                break
            reached += 1
        score = round(sum(1 for d in details if d["correct"]) / len(details), 2)
        display = f"{activity.solution['display']} (marche atteinte : {reached}/{len(details)})"
        return _one(activity, score, ErrorType.KNOWLEDGE, display, details=details)


# --------------------------------------------------------------------------- #
# Le train des mots (CP-CE1)
# --------------------------------------------------------------------------- #


def _young_french(unit: KnowledgeUnit) -> bool:
    return (unit.grade is None or unit.grade in YOUNG) and FrenchTopic.SYLLABLES in _french(unit)


class WordTrainResponse(ResponseModel):
    order: list[str] = Field(max_length=8)


class WordTrain(ActivityType):
    code = ActivityCode.WORD_TRAIN
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2})
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return _young_french(unit)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        word = rng.choice(SYLLABLE_WORDS[difficulty])
        others = [s for w in SYLLABLE_WORDS[difficulty] if w != word for s in w if s not in word]
        wagons = _ids("v", [*word, *rng.sample(sorted(set(others)), 2)])
        order = [w["id"] for w in wagons[: len(word)]]
        rng.shuffle(wagons)
        payload = {
            "prompt": "Écoute le mot. Accroche les wagons dans l'ordre.",
            "say": "".join(word),
            "lang": "fr-FR",
            "wagons": wagons,
            "length": len(word),
        }
        return payload, {"order": order, "display": "-".join(word), **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        order = parse_response(WordTrainResponse, response).order
        if not set(order) <= {w["id"] for w in activity.payload["wagons"]}:
            raise InvalidResponse("wagon inconnu")
        expected: list[str] = activity.solution["order"]
        score = 1.0 if order == expected else 0.0
        return _one(activity, score, ErrorType.IMPRECISION, activity.solution["display"])


# --------------------------------------------------------------------------- #
# Compte et touche (CP-CE1)
# --------------------------------------------------------------------------- #

OBJECTS = ("🍎", "⭐", "🐟", "🎈", "🚗", "🌼")
COUNT_RANGES = {1: (3, 10), 2: (11, 20)}


class CountTouchResponse(ResponseModel):
    selected: list[str] = Field(max_length=30)


class CountTouch(ActivityType):
    code = ActivityCode.COUNT_TOUCH
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2})
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.subject == Subject.MATH and unit.grade in YOUNG and bool(_topics(unit) & NUMBER_TOPICS)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        low, high = COUNT_RANGES[difficulty]
        target = rng.randint(low, high)
        shown = min(30, target + rng.randint(3, 8))
        emoji = rng.choice(OBJECTS)
        payload = {
            "prompt": f"Touche {target} objets.",
            "say": str(target),
            "target": target,
            "emoji": emoji,
            "objects": [f"o{i}" for i in range(1, shown + 1)],
        }
        # Inventé par le code (pas une question de la leçon) : la séance commence par la leçon.
        solution = {"target": target, "display": f"{target} objets", "from_lesson": False, **feedback(unit)}
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        selected = parse_response(CountTouchResponse, response).selected
        if not set(selected) <= set(activity.payload["objects"]) or len(set(selected)) != len(selected):
            raise InvalidResponse("objet inconnu ou touché deux fois")
        target: int = activity.solution["target"]
        score = 1.0 if len(selected) == target else 0.0
        display = f"Il fallait toucher {target} objets (tu en as touché {len(selected)})."
        return _one(activity, score, ErrorType.CALCULATION, display)
