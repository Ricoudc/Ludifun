"""Registre des types d'activités.

Ajouter un jeu = écrire une classe `ActivityType` et l'ajouter à `default_registry()`.
Le composeur, la notation et la mémorisation n'ont pas à changer.
"""

from app.domain.activities.base import ActivityCode, ActivityType, BuiltActivity
from app.domain.activities.classify import Classify
from app.domain.activities.figures import Coloring, MapLocate
from app.domain.activities.fill_blank import FillBlank
from app.domain.activities.find_match import FindMatch
from app.domain.activities.flashcard import Flashcard
from app.domain.activities.lucky import Box, RandomCards, Wheel
from app.domain.activities.match import Match
from app.domain.activities.mcq import Mcq
from app.domain.activities.memory import Memory
from app.domain.activities.open_question import OpenQuestionActivity
from app.domain.activities.ordering import Order, Timeline
from app.domain.activities.pictures import PictureFind, PictureMatch
from app.domain.activities.speed_challenge import SpeedChallenge
from app.domain.activities.spelling import Dictation, Scramble, WordFlash
from app.domain.activities.true_false import TrueFalse
from app.domain.activities.unjumble import Unjumble
from app.domain.knowledge import KnowledgeUnit


class UnknownActivity(KeyError):
    pass


class ActivityRegistry:
    def __init__(self, types: list[ActivityType]) -> None:
        self._types: dict[ActivityCode, ActivityType] = {}
        for activity_type in types:
            if activity_type.code in self._types:
                raise ValueError(f"type d'activité enregistré deux fois : {activity_type.code}")
            self._types[activity_type.code] = activity_type

    def get(self, code: str) -> ActivityType:
        try:
            return self._types[ActivityCode(code)]
        except (ValueError, KeyError) as exc:
            raise UnknownActivity(code) from exc

    def for_activity(self, activity: BuiltActivity) -> ActivityType:
        return self.get(activity.type)

    @property
    def codes(self) -> list[ActivityCode]:
        return list(self._types)

    def all(self) -> list[ActivityType]:
        return list(self._types.values())

    def single_options(self, unit: KnowledgeUnit) -> list[tuple[ActivityCode, int]]:
        """Activités (type, difficulté) constructibles sur cette seule notion."""
        return [
            (t.code, difficulty)
            for t in self._types.values()
            if not t.multi_knowledge
            for difficulty in sorted(t.difficulties)
            if t.can_build([unit], difficulty)
        ]

    def formats_for(self, unit: KnowledgeUnit) -> set[ActivityCode]:
        """Types d'activités auxquels cette notion peut participer (seule ou avec d'autres)."""
        return {t.code for t in self._types.values() if t.accepts(unit)}


def default_registry() -> ActivityRegistry:
    return ActivityRegistry(
        [
            Mcq(),
            TrueFalse(),
            FillBlank(),
            Match(),
            SpeedChallenge(),
            Flashcard(),
            OpenQuestionActivity(),
            # Activités graphiques (étape 21)
            Order(),
            Classify(),
            Timeline(),
            Memory(),
            # Activités sur une figure (étape 22)
            MapLocate(),
            Coloring(),
            # Jeux d'orthographe
            WordFlash(),
            Scramble(),
            Dictation(),
            # Jeux en plus (étape 26)
            Unjumble(),
            FindMatch(),
            Wheel(),
            Box(),
            RandomCards(),
            # Apprendre par l'image (étape 28)
            PictureMatch(),
            PictureFind(),
        ]
    )
