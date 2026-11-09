"""La matière qui décroche (§5.75) : sa note moyenne baisse sur plusieurs semaines.

On compare, matière par matière, la note moyenne des séances terminées des deux dernières
semaines à celle des deux semaines d'avant. Une matière décroche quand la baisse atteint
`DROP` points sur 10, avec au moins `MIN_SESSIONS` séances de chaque côté : une seule mauvaise
séance ne fait pas une tendance. S'il y en a plusieurs, la plus forte baisse.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.knowledge import Subject

HALF = 2  # semaines de chaque côté
DROP = 1.5  # baisse minimale de la note moyenne sur 10
MIN_SESSIONS = 2  # séances terminées au moins, de chaque côté

SUBJECT_NAMES = {
    Subject.FRENCH: "le français",
    Subject.MATH: "les maths",
    Subject.HISTORY: "l'histoire",
    Subject.GEOGRAPHY: "la géographie",
    Subject.SCIENCE: "les sciences",
    Subject.ENGLISH: "l'anglais",
    Subject.CIVICS: "l'EMC",
    Subject.OTHER: "les autres matières",
}


@dataclass(frozen=True)
class SessionScore:
    subject: str
    week: date  # lundi de la semaine de la séance
    score: float  # note sur 10


@dataclass(frozen=True)
class Slipping:
    subject: str
    before: float  # moyenne des 2 semaines d'avant
    after: float  # moyenne des 2 dernières semaines

    @property
    def name(self) -> str:
        try:
            return SUBJECT_NAMES[Subject(self.subject)]
        except ValueError:
            return self.subject


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


def slipping_subject(scores: Iterable[SessionScore], current_week: date) -> Slipping | None:
    recent_from = current_week - timedelta(weeks=HALF - 1)
    older_from = recent_from - timedelta(weeks=HALF)
    recent: dict[str, list[float]] = defaultdict(list)
    older: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        if recent_from <= s.week <= current_week:
            recent[s.subject].append(s.score)
        elif older_from <= s.week < recent_from:
            older[s.subject].append(s.score)
    found = [
        Slipping(subject, _mean(older[subject]), _mean(values))
        for subject, values in recent.items()
        if len(values) >= MIN_SESSIONS and len(older[subject]) >= MIN_SESSIONS
    ]
    found = [s for s in found if s.before - s.after >= DROP]
    return max(found, key=lambda s: (s.before - s.after, s.subject), default=None)
