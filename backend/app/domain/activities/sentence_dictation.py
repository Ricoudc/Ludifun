"""« Dictée de phrases » (SENTENCE_DICTATION) : le téléphone lit une phrase qui emploie un mot de
la liste, puis la relit morceau par morceau et une dernière fois en entier, comme en classe ;
l'enfant l'écrit sans l'avoir vue. Rien n'est demandé à l'IA pendant la séance.

La phrase vient de la notion « mot à savoir écrire » (matériel `spelling`, contrôlé) : d'abord une
phrase de la leçon qui contient le mot (§5.58, `statement` ou affirmation vraie), sinon la phrase
d'aide du matériel, « ___ » remplacé par le mot. Sa longueur suit la classe (6 mots au plus au CP,
8 au CE1…) ; une phrase avec des chiffres (lus « trois », écrits « 3 ») ou des guillemets n'est
pas dictée.

Correction mot à mot, alignée (un mot oublié ne décale pas les suivants) : orthographe stricte
(accents), sans compter les majuscules ni la ponctuation, que la voix ne dit pas. Le score de
l'enfant est la part des mots justes ; la preuve de maîtrise de la notion ne regarde que le mot
de la liste, celui qui est appris.
"""

import math
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
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.activities.spelling import same_spelling
from app.domain.activities.unjumble import reading_groups
from app.domain.errors import written_answer_error
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeUnit

MIN_WORDS = 3
# Mots d'une phrase dictée, au plus, selon la classe ; collège ou classe inconnue : 15.
MAX_WORDS: dict[SchoolGrade, int] = {
    SchoolGrade.CP: 6,
    SchoolGrade.CE1: 8,
    SchoolGrade.CE2: 10,
    SchoolGrade.CM1: 12,
    SchoolGrade.CM2: 14,
}
DEFAULT_MAX_WORDS = 15
MAX_DETAILS = 8  # mots ratés montrés à l'enfant
# Lettres, espaces, apostrophes, traits d'union et ponctuation simple : rien que la voix lise mal.
_DICTABLE = re.compile(r"^[^\W\d_]+(?:[\s'’\-,.!?]+[^\W\d_]*)*$")
_EDGES = '.,;:!?…«»"()[]'


class SentenceDictationResponse(ResponseModel):
    text: str = Field(max_length=400)


def words_of(text: str) -> list[str]:
    """Les mots d'une phrase écrite, sans la ponctuation ; « l'hôpital » donne « l' » et
    « hôpital » (l'enfant peut taper « l' hôpital »)."""
    text = re.sub(r"(['’ʼ])\s+", r"\1", text.replace("’", "'").replace("ʼ", "'"))
    words: list[str] = []
    for token in text.split():
        for part in re.split(r"(?<=')", token):
            part = part.strip(_EDGES)
            if any(c.isalnum() for c in part):
                words.append(part)
    return words


def _max_words(unit: KnowledgeUnit) -> int:
    return MAX_WORDS.get(unit.grade, DEFAULT_MAX_WORDS) if unit.grade else DEFAULT_MAX_WORDS


def _position(words: list[str], target: list[str]) -> int | None:
    """Où le mot de la liste (un ou plusieurs mots) se trouve dans la phrase."""
    for start in range(len(words) - len(target) + 1):
        if all(same_spelling(words[start + i], t) for i, t in enumerate(target)):
            return start
    return None


def _usable(sentence: str, word: str, unit: KnowledgeUnit) -> bool:
    text = " ".join(sentence.split())
    return (
        bool(_DICTABLE.match(text))
        and MIN_WORDS <= len(text.split()) <= _max_words(unit)
        and _position(words_of(text), words_of(word)) is not None
    )


def sentences_of(unit: KnowledgeUnit) -> tuple[list[str], list[str]]:
    """Les phrases à dicter : celles de la leçon, puis celle du matériel (phrase d'aide)."""
    spelling = unit.material.spelling
    if spelling is None:
        return [], []
    word = spelling.word
    lesson: list[str] = []
    for text in [unit.item.statement, *unit.material.true_statements]:
        sentence = " ".join(text.split())
        if _usable(sentence, word, unit) and sentence not in lesson:
            lesson.append(sentence)
    helper = spelling.sentence.replace("___", word) if spelling.sentence else None
    invented = [helper] if helper and _usable(helper, word, unit) and helper not in lesson else []
    return lesson, invented


def align(expected: list[str], given: list[str]) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Chaque mot attendu et le mot écrit à sa place (None : oublié), puis les mots en trop.

    Distance d'édition sur les mots : un mot oublié ou ajouté ne fait pas compter faux tous les
    suivants."""
    n, m = len(expected), len(given)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = same_spelling(given[j - 1], expected[i - 1])
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if same else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )
    pairs: list[tuple[str, str | None]] = []
    extra: list[str] = []
    i, j = n, m
    while i or j:
        if i and j:
            same = same_spelling(given[j - 1], expected[i - 1])
            if cost[i][j] == cost[i - 1][j - 1] + (0 if same else 1):
                pairs.append((expected[i - 1], given[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append((expected[i - 1], None))
            i -= 1
        else:
            extra.append(given[j - 1])
            j -= 1
    return pairs[::-1], extra[::-1]


class SentenceDictation(ActivityType):
    code = ActivityCode.SENTENCE_DICTATION
    knowledge_types = ALL_TYPES
    difficulties = frozenset({3})  # après la dictée du mot seul
    base_duration_s = 60

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        lesson, invented = sentences_of(unit)
        return bool(lesson or invented)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        assert unit.material.spelling is not None
        lesson, invented = sentences_of(unit)
        sentence = rng.choice(lesson or invented)  # une autre phrase d'une séance à l'autre
        words = sentence.split()
        # Morceaux relus un à un : groupes de lecture (« le petit chat | dort | sur le lit »).
        chunks = reading_groups(words, glue=True, limit=max(2, math.ceil(len(words) / 3)))
        payload = {
            "prompt": "Écoute la phrase, puis écris-la.",
            "sentence": sentence,  # à lire à voix haute, jamais affichée (sauf sans voix)
            "chunks": chunks,
            "word_count": len(words_of(sentence)),
            "show_ms": 2000 + 500 * len(words),  # sans voix française : affichée ce temps-là
        }
        solution = {
            "sentence": sentence,
            "display": sentence,
            "word": unit.material.spelling.word,
            "from_lesson": bool(lesson),
            **feedback(unit),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given_text = parse_response(SentenceDictationResponse, response).text
        sentence: str = activity.solution["sentence"]
        expected = words_of(sentence)
        pairs, extra = align(expected, words_of(given_text))
        right = [g is not None and same_spelling(g, e) for e, g in pairs]
        score = sum(right) / (len(expected) + len(extra))
        if not all(right) or extra:
            score = min(score, 0.9)
        # La notion est le mot de la liste : la maîtrise ne regarde que lui.
        word: str = activity.solution["word"]
        target = words_of(word)
        start = _position(expected, target)
        knowledge = activity.knowledge_ids[0]
        if start is None:  # phrase enregistrée par une version plus ancienne : toute la phrase
            word_ok, written = score >= 1, given_text
        else:
            span = range(start, start + len(target))
            word_ok = all(right[k] for k in span)
            written = " ".join(pairs[k][1] or "" for k in span)
        details: list[dict[str, Any]] = [
            {"text": g if g is not None else "mot oublié", "expected": e, "correct": False}
            for (e, g), ok in zip(pairs, right, strict=True)
            if not ok
        ] + [{"text": f"{g} (mot en trop)", "correct": False} for g in extra]
        return Grade(
            score=score,
            evidence={knowledge: 1.0 if word_ok else 0.0},
            errors={} if word_ok else {knowledge: written_answer_error(written, [word])},
            correct_answer=sentence,
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
            details=details[:MAX_DETAILS],
        )
