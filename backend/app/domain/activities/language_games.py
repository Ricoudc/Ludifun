"""Deux jeux de langue fabriqués par le code, avec une image et la voix du téléphone (§5.62) :

- « Le bon son » (SOUNDS), CP-CE1 : « l__p » 🐺 — l'enfant écoute le mot et choisit les lettres
  du son qui manque (ou, on, an, in, oi). Difficulté 1 : deux sons ; 2 : trois sons ; 3 :
  comment s'écrit le son (an, en, am, em…).
- « Anglais en images » (ENGLISH_WORDS) : couleurs, nombres, jours, animaux… Difficulté 1 :
  voir l'image, choisir le mot anglais ; 2 : écouter le mot anglais, toucher l'image ; 3 :
  traduire le mot français.

Un seul écran pour les deux : une carte (image, mot à compléter, bouton 🔊) et des boutons de
réponse. Les mots viennent de banques écrites à la main (`phonics`, `english`) ; ceux que la
leçon écrit passent d'abord (§5.58). Rien n'est demandé à l'IA.
"""

import random
from typing import Any, ClassVar

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    feedback,
    parse_response,
)
from app.domain.activities.word_games import AnswersResponse
from app.domain.english import EnglishTheme, EnglishWord, english_themes, lesson_words
from app.domain.english import words_of as english_words_of
from app.domain.errors import ErrorType
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeUnit, Subject
from app.domain.phonics import CONFUSABLE, GRAPHIES, SOUNDS, SoundWord, lesson_sounds, words_of
from app.domain.text import normalize

FRENCH_VOICE = "fr-FR"
ENGLISH_VOICE = "en-GB"
# Les sons s'apprennent au CP et au CE1, se révisent au CE2 ; une classe inconnue n'exclut rien.
SOUND_GRADES = frozenset({SchoolGrade.CP, SchoolGrade.CE1, SchoolGrade.CE2})


def _grade_rounds(activity: BuiltActivity, response: dict[str, Any], error: ErrorType) -> Grade:
    """Chaque carte compte ; tout juste : 1, sinon la part de justes × 0,8."""
    answers = dict(parse_response(AnswersResponse, response).answers)
    cards = {i["id"]: i for i in activity.payload["items"]}
    if not set(answers) <= set(cards):
        raise InvalidResponse("carte inconnue")
    expected: dict[str, str] = activity.solution["expected"]
    shown: dict[str, str] = activity.solution["shown"]
    correct = {cid: answers.get(cid) == answer for cid, answer in expected.items()}
    details: list[dict[str, Any]] = [
        {"id": cid, "correct": ok, "expected": shown[cid]} for cid, ok in correct.items()
    ]
    right = sum(correct.values())
    score = 1.0 if right == len(details) else round(right / len(details) * 0.8, 2)
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
# Le bon son
# --------------------------------------------------------------------------- #


def _sounds(unit: KnowledgeUnit) -> list[str]:
    if unit.subject != Subject.FRENCH or (unit.grade is not None and unit.grade not in SOUND_GRADES):
        return []
    return lesson_sounds(unit.item.corpus())


def _lesson_first(words: list[SoundWord], corpus: str, rng: random.Random) -> list[SoundWord]:
    """Les mots que la leçon écrit d'abord, puis les autres au hasard."""
    written = set(normalize(corpus).split())
    shuffled = rng.sample(words, len(words))
    return sorted(shuffled, key=lambda w: normalize(w.word) not in written)


def _plain(sound: str) -> list[SoundWord]:
    """Les mots où le son s'écrit le plus simplement (ou, on, an, in, oi) : niveaux 1 et 2. Les
    autres écritures (« pompier », « serpent », « main ») attendent le niveau 3."""
    return [w for w in words_of(sound) if w.graphy == GRAPHIES[sound][0] and not w.graphies_only]


class Sounds(ActivityType):
    code = ActivityCode.SOUNDS
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 35
    CARDS: ClassVar[dict[int, int]] = {1: 4, 2: 5, 3: 5}
    CHOICES: ClassVar[dict[int, int]] = {1: 2, 2: 3}

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_sounds(unit))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        studied = _sounds(unit)
        corpus = unit.item.corpus()
        spelled = [s for s in studied if len(GRAPHIES[s]) > 1]
        if difficulty == 3 and spelled:
            # Comment s'écrit le son : « serp__t » → an, en, am ou em ?
            pool = _lesson_first([w for s in spelled for w in words_of(s)], corpus, rng)
            # Moitié d'écritures rares (en, am, ain…) : la réponse n'est pas toujours la plus courante.
            rare = [w for w in pool if w.graphy != GRAPHIES[w.sound][0]]
            half = self.CARDS[3] // 2 + 1
            picked = (
                rare[:half] + [w for w in pool if w not in rare[:half]][: self.CARDS[3] - len(rare[:half])]
            )
            rng.shuffle(picked)
            cards = [(w, list(GRAPHIES[w.sound])) for w in picked]
            prompt = "Écoute le mot. Choisis comment s'écrit le son."
        else:
            size = self.CHOICES.get(difficulty, 4)
            sounds = list(studied[:size])
            for sound in (*CONFUSABLE[studied[0]], *SOUNDS):
                if len(sounds) < size and sound not in sounds:
                    sounds.append(sound)
            # Surtout les sons de la leçon, et au moins un mot d'un autre son : la réponse change.
            own = _lesson_first([w for s in studied for w in _plain(s)], corpus, rng)
            others = [w for s in sounds if s not in studied for w in _plain(s)]
            rng.shuffle(others)
            n = self.CARDS[difficulty]
            mine = own[: n - max(1, n // 3)] if others else own[:n]
            picked = mine + others[: n - len(mine)]
            rng.shuffle(picked)
            cards = [(w, [w.graphy, *(GRAPHIES[s][0] for s in sounds if s != w.sound)]) for w in picked]
            prompt = "Écoute le mot. Choisis le son qui manque."
        items, expected, shown = [], {}, {}
        for n, (word, choices) in enumerate(cards, start=1):
            rng.shuffle(choices)
            cid = f"m{n}"
            items.append(
                {
                    "id": cid,
                    "picture": word.picture,
                    "text": word.masked,
                    "say": word.word,
                    "lang": FRENCH_VOICE,
                    "choices": choices,
                }
            )
            expected[cid] = word.graphy
            shown[cid] = word.word
        payload = {"prompt": prompt, "items": items}
        display = ", ".join(w.word for w, _ in cards)
        return payload, {"expected": expected, "shown": shown, "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        return _grade_rounds(activity, response, ErrorType.CONFUSION)


# --------------------------------------------------------------------------- #
# Anglais en images
# --------------------------------------------------------------------------- #


def _english(unit: KnowledgeUnit) -> list[EnglishTheme]:
    if unit.subject != Subject.ENGLISH:
        return []
    return english_themes(unit.item.corpus())


class EnglishWords(ActivityType):
    code = ActivityCode.ENGLISH_WORDS
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 35
    CARDS: ClassVar[dict[int, int]] = {1: 4, 2: 5, 3: 6}
    CHOICES: ClassVar[dict[int, int]] = {1: 3, 2: 3, 3: 4}

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_english(unit))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        themes = _english(unit)
        pool = [w for theme in themes for w in english_words_of(theme)]
        written = {w.english for w in lesson_words(unit.item.corpus())}
        ordered = sorted(rng.sample(pool, len(pool)), key=lambda w: w.english not in written)
        picked = ordered[: self.CARDS[difficulty]]
        items, expected, shown = [], {}, {}
        for n, word in enumerate(picked, start=1):
            same = [w for w in english_words_of(word.theme) if w != word]
            wrong = rng.sample(same, min(len(same), self.CHOICES[difficulty] - 1))
            cid = f"e{n}"
            card: dict[str, Any] = {"id": cid}
            if difficulty == 2:
                # Écouter le mot anglais, toucher l'image (le mot français sans image).
                options = [_face(w) for w in (word, *wrong)]
                card |= {"text": "🔊 ?", "say": word.english, "lang": ENGLISH_VOICE}
                answer = _face(word)
            else:
                options = [w.english for w in (word, *wrong)]
                if difficulty == 1 and word.picture is not None:
                    card |= {"picture": word.picture, "text": ""}
                else:
                    card |= {"text": word.french}
                answer = word.english
            rng.shuffle(options)
            card["choices"] = options
            if difficulty != 2:
                # Les choix lus en anglais, dans l'ordre des boutons : on apprend à les prononcer.
                card |= {"say": ", ".join(options), "lang": ENGLISH_VOICE}
            items.append(card)
            expected[cid] = answer
            shown[cid] = f"{word.english} = {word.french}"
        prompt = {
            1: "Regarde l'image. Choisis le mot anglais.",
            2: "Écoute le mot anglais. Touche la bonne image.",
            3: "Choisis le mot anglais qui veut dire la même chose.",
        }[difficulty]
        display = ", ".join(f"{w.english} ({w.french})" for w in picked)
        payload = {"prompt": prompt, "items": items}
        return payload, {"expected": expected, "shown": shown, "display": display, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        return _grade_rounds(activity, response, ErrorType.KNOWLEDGE)


def _face(word: EnglishWord) -> str:
    """Ce qui montre le mot sans le dire en anglais : son image, sinon le mot français."""
    return word.picture or word.french
