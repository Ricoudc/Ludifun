"""Jeux fabriqués par le code pour toutes les matières, en plus des quiz :

- « Chasse aux mots » (WORD_HUNT) : toucher tous les éléments d'une catégorie parmi d'autres
  (« Touche tous les animaux vivipares », « Touche tous les noms »). Les catégories viennent de
  la leçon (classement, jeu de tri vérifié) ou, en français, du lexique du code.
- « Conjugaison » (CONJUGATION) : compléter le tableau d'un verbe ; le code conjugue.
- « Homophones » (HOMOPHONE) : a ou à, et ou est… dans des phrases écrites à la main.

La bonne réponse est toujours connue du code ; rien n'est demandé à l'IA pendant la séance.
"""

import random
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
from app.domain.activities.ordering import grade_order
from app.domain.equivalence import separate_boxes
from app.domain.errors import ErrorType
from app.domain.french import (
    ALPHABET_WORDS,
    EARLY_PAIRS,
    HOMOPHONES,
    LEXICON,
    FrenchTopic,
    Tense,
    conjugate,
    french_topics,
    homophone_pairs,
    pronoun,
    tense_of,
    verbs_of,
)
from app.domain.knowledge import ClassificationAttributes, KnowledgeType, KnowledgeUnit, Subject, Theme
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.text import normalize

# Thème choisi par l'IA (§5.47) → thème de français des jeux.
_BY_THEME = {
    Theme.CONJUGATION: FrenchTopic.CONJUGATION,
    Theme.HOMOPHONES: FrenchTopic.HOMOPHONES,
    Theme.WORD_NATURE: FrenchTopic.NATURE,
    Theme.NUMBER: FrenchTopic.NUMBER,
    Theme.GENDER: FrenchTopic.GENDER,
    Theme.ALPHABET: FrenchTopic.ALPHABET,
}


def _french(unit: KnowledgeUnit) -> list[FrenchTopic]:
    """Le thème choisi par l'IA s'il y en a un, puis ceux que désignent les mots de la notion."""
    if unit.subject != Subject.FRENCH:
        return []
    found = french_topics(unit.item.corpus())
    named = _BY_THEME.get(unit.item.theme) if unit.item.theme is not None else None
    return found if named is None else [named, *(topic for topic in found if topic is not named)]


def _result(activity: BuiltActivity, score: float, error: ErrorType, details: list[dict[str, Any]]) -> Grade:
    knowledge_id, solution = activity.knowledge_ids[0], activity.solution
    return Grade(
        score=score,
        evidence={knowledge_id: score},
        errors={knowledge_id: error} if score < 1 else {},
        correct_answer=solution["display"],
        tip=solution.get("tip"),
        explanation=solution.get("explanation"),
        details=details,
    )


# --------------------------------------------------------------------------- #
# Chasse aux mots
# --------------------------------------------------------------------------- #

HUNT_SIZE = {1: 6, 2: 9, 3: 12}


def _lexicon_prompt(name: str) -> str:
    """« Touche tous les noms. » ; « Touche les groupes de mots au pluriel. »"""
    if name.startswith("au "):
        return f"Touche les groupes de mots {name}."
    return f"Touche tous les {name}."


class SelectedResponse(ResponseModel):
    selected: list[str] = Field(max_length=16)


class WordHunt(ActivityType):
    code = ActivityCode.WORD_HUNT
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 25

    @staticmethod
    def _categories(unit: KnowledgeUnit) -> tuple[list[tuple[str, list[str]]], bool]:
        """Les catégories (nom, éléments), et vrai si elles viennent du lexique du français."""
        found: list[tuple[str, list[str]]] = []
        if unit.type == KnowledgeType.CLASSIFICATION:
            attributes = ClassificationAttributes.model_validate(unit.item.attributes)
            found = [(c.name, list(c.members)) for c in attributes.categories]
        elif unit.material.sorting is not None:
            found = [(c.name, list(c.members)) for c in unit.material.sorting.categories]
        if found:
            return found, False
        for topic in _french(unit):
            if topic in LEXICON:
                return [(name, list(words)) for name, words in LEXICON[topic].items()], True
        return [], False

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        categories, _ = self._categories(unit)
        members = [normalize(m) for _, items in categories for m in items]
        # Un élément dans deux catégories rendrait la chasse ambiguë.
        return (
            len(categories) >= 2
            and len(set(members)) == len(members)
            and separate_boxes([items for _, items in categories])
            and any(len(items) >= 2 and len(members) - len(items) >= 3 for _, items in categories)
        )

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        categories, lexicon = self._categories(unit)
        usable = [
            (name, items)
            for name, items in categories
            if len(items) >= 2 and sum(len(i) for n, i in categories if n != name) >= 3
        ]
        name, members = rng.choice(usable)
        size = HUNT_SIZE[difficulty]
        targets = rng.sample(members, min(len(members), max(2, size // 3)))
        others = [m for n, items in categories if n != name for m in items]
        decoys = rng.sample(others, min(len(others), size - len(targets)))
        words = [*targets, *decoys]
        rng.shuffle(words)
        ids = {word: f"w{i}" for i, word in enumerate(words, start=1)}
        prompt = _lexicon_prompt(name) if lexicon else f"Touche tout ce qui va dans « {name} »."
        payload = {"prompt": prompt, "words": [{"id": ids[w], "text": w} for w in words]}
        listed = ", ".join(sorted(targets, key=words.index))
        return payload, {
            "expected": sorted(ids[t] for t in targets),
            "display": f"Il fallait toucher {listed}.",
            **feedback(unit),
        }

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        selected = set(parse_response(SelectedResponse, response).selected)
        names = {w["id"] for w in activity.payload["words"]}
        if not selected <= names:
            raise InvalidResponse("mot inconnu")
        expected = set(activity.solution["expected"])
        found = len(selected & expected) - len(selected - expected)
        score = 1.0 if selected == expected else max(0.0, round(found / len(expected), 2) - 0.25)
        return _result(activity, score, ErrorType.CONFUSION, [])


# --------------------------------------------------------------------------- #
# Conjugaison
# --------------------------------------------------------------------------- #

TENSE_WORDS = {
    Tense.PRESENT: "au présent",
    Tense.FUTUR: "au futur",
    Tense.IMPARFAIT: "à l'imparfait",
    Tense.PASSE_COMPOSE: "au passé composé",
}


def _with_pronoun(person: int, form: str) -> str:
    """« je chante », « j'aime »."""
    who = pronoun(person, form)
    return f"{who}{form}" if who.endswith("'") else f"{who} {form}"


class AnswersResponse(ResponseModel):
    answers: list[tuple[str, str]] = Field(max_length=10)


class Conjugation(ActivityType):
    code = ActivityCode.CONJUGATION
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 45

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        if FrenchTopic.CONJUGATION not in _french(unit):
            return False
        tense = tense_of(unit.item.corpus())
        return bool(verbs_of(unit.item.corpus(), tense))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        tense = tense_of(unit.item.corpus())
        verb = rng.choice(verbs_of(unit.item.corpus(), tense))
        forms = conjugate(verb, tense)
        assert forms is not None
        persons = [0, 1, 2, 3] if difficulty == 1 else list(range(6))
        rows = [{"id": f"p{p}", "text": pronoun(p, forms[p])} for p in persons]
        chips = [forms[p] for p in persons]
        if difficulty == 3:
            # Deux formes d'un autre temps : il faut reconnaître le bon temps.
            others = [t for t in Tense if t is not tense and conjugate(verb, t)]
            other = conjugate(verb, rng.choice(others)) if others else None
            chips += [f for f in (other or ()) if f not in chips][:2]
        rng.shuffle(chips)
        payload = {
            "prompt": f"Conjugue « {verb} » {TENSE_WORDS[tense]}.",
            "word": verb,
            "items": rows,
            "choices": [{"id": f"c{i}", "text": text} for i, text in enumerate(chips, start=1)],
        }
        expected = {f"p{p}": forms[p] for p in persons}
        written = ", ".join(_with_pronoun(p, forms[p]) for p in persons)
        return payload, {"expected": expected, "display": f"{written}.", **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        chips = {c["id"]: c["text"] for c in activity.payload["choices"]}
        answers = dict(parse_response(AnswersResponse, response).answers)
        rows = {r["id"] for r in activity.payload["items"]}
        if not set(answers) <= rows or not set(answers.values()) <= set(chips):
            raise InvalidResponse("case ou forme inconnue")
        expected: dict[str, str] = activity.solution["expected"]
        details = [
            {"id": row, "correct": chips.get(answers.get(row, ""), "") == form, "expected": form}
            for row, form in expected.items()
        ]
        right = sum(d["correct"] for d in details)
        score = 1.0 if right == len(details) else round(right / len(details) * 0.8, 2)
        return _result(activity, score, ErrorType.KNOWLEDGE, details)


# --------------------------------------------------------------------------- #
# Homophones
# --------------------------------------------------------------------------- #

SENTENCES = {1: 4, 2: 5, 3: 6}


class Homophones(ActivityType):
    code = ActivityCode.HOMOPHONE
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 30

    @staticmethod
    def _pairs(unit: KnowledgeUnit) -> list[tuple[str, str]]:
        if unit.subject != Subject.FRENCH:
            return []
        pairs = homophone_pairs(unit.item.corpus())
        if not pairs and unit.item.theme == Theme.HOMOPHONES:
            pairs = list(HOMOPHONES)  # une leçon d'homophones qui n'en nomme aucun
        if unit.grade in (SchoolGrade.CP, SchoolGrade.CE1) and len(pairs) > len(EARLY_PAIRS):
            pairs = [p for p in pairs if p in EARLY_PAIRS]
        return pairs

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(self._pairs(unit))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        pairs = self._pairs(unit)
        chosen = [rng.choice(pairs)] if difficulty == 1 else pairs
        pool = [(pair, blank) for pair in chosen for blank in HOMOPHONES[pair]]
        picked = rng.sample(pool, min(len(pool), SENTENCES[difficulty]))
        items = [
            {"id": f"s{i}", "text": blank.sentence, "choices": list(pair)}
            for i, (pair, blank) in enumerate(picked, start=1)
        ]
        expected = {f"s{i}": blank.answer for i, (_, blank) in enumerate(picked, start=1)}
        filled = " ".join(blank.sentence.replace("___", blank.answer.upper()) for _, blank in picked)
        payload = {"prompt": "Choisis le bon mot pour chaque phrase.", "items": items}
        return payload, {"expected": expected, "display": filled, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        answers = dict(parse_response(AnswersResponse, response).answers)
        sentences = {i["id"]: i for i in activity.payload["items"]}
        if not set(answers) <= set(sentences):
            raise InvalidResponse("phrase inconnue")
        expected: dict[str, str] = activity.solution["expected"]
        details = [
            {
                "id": sid,
                "correct": answers.get(sid) == word,
                "expected": sentences[sid]["text"].replace("___", word),
            }
            for sid, word in expected.items()
        ]
        right = sum(d["correct"] for d in details)
        score = 1.0 if right == len(details) else round(right / len(details) * 0.8, 2)
        return _result(activity, score, ErrorType.CONFUSION, details)


# --------------------------------------------------------------------------- #
# Ordre alphabétique
# --------------------------------------------------------------------------- #

ALPHA_SIZE = {1: 4, 2: 5, 3: 6}


class AlphaOrder(ActivityType):
    """Ranger des mots dans l'ordre alphabétique (même écran que « remettre dans l'ordre »).
    Difficulté 1 : premières lettres toutes différentes ; 2 : deux mots commencent par la même
    lettre ; 3 : deux mots ont les mêmes deux premières lettres."""

    code = ActivityCode.ALPHA_ORDER
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 30

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return FrenchTopic.ALPHABET in _french(unit)

    @staticmethod
    def _words(difficulty: int, rng: random.Random) -> list[str]:
        same = {1: 0, 2: 1, 3: 2}[difficulty]  # lettres communes au début d'une paire
        for _ in range(500):
            words = rng.sample(ALPHABET_WORDS, ALPHA_SIZE[difficulty])
            starts = [normalize(w)[: max(1, same)] for w in words]
            if same == 0 and len(set(starts)) == len(starts):
                return words
            if same and len(set(starts)) < len(starts):
                return words
        raise ValueError("mots impossibles")  # pragma: no cover

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        words = self._words(difficulty, rng)
        ordered = sorted(words, key=normalize)
        ids = [f"s{i}" for i in range(1, len(ordered) + 1)]
        texts = dict(zip(ids, ordered, strict=True))
        shuffled = list(ids)
        while shuffled == ids:
            rng.shuffle(shuffled)
        payload = {
            "prompt": "Range les mots dans l'ordre alphabétique.",
            "items": [{"id": i, "text": texts[i]} for i in shuffled],
        }
        return payload, {"order": ids, "texts": texts, "display": " → ".join(ordered), **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        details, score = grade_order(activity, response)
        return _result(activity, score, ErrorType.METHOD, details)
