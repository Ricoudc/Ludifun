"""Appels à l'IA de ce serveur (mémoire du processus), pour la page /suivi et l'écran d'analyse.

Pendant une analyse : l'appel en cours et les étapes déjà faites, avec leur durée et leur
résultat. Quand l'analyse est enregistrée (journal `ai_runs`), sa trace en mémoire est effacée.
"""

import itertools
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app import clock

# Fin d'un appel : statut (ok, error, invalid_output…) et message d'erreur éventuel.
Finish = Callable[[str, str | None], None]


@dataclass(frozen=True)
class LiveCall:
    lesson_id: uuid.UUID | None
    stage: str
    model: str
    started_at: datetime


@dataclass(frozen=True)
class DoneCall:
    stage: str
    model: str
    seconds: int
    status: str
    message: str | None


class LiveCalls:
    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._calls: dict[int, LiveCall] = {}
        self._done: dict[uuid.UUID, list[DoneCall]] = defaultdict(list)
        self._ids = itertools.count()

    def track(self, lesson_id: uuid.UUID | None, stage: str, model: str) -> Finish:
        key = next(self._ids)
        call = LiveCall(lesson_id, stage, model, self._now())
        self._calls[key] = call

        def finish(status: str, message: str | None) -> None:
            if self._calls.pop(key, None) is None:
                return
            if lesson_id is not None:
                seconds = max(0, round((self._now() - call.started_at).total_seconds()))
                self._done[lesson_id].append(DoneCall(stage, model, seconds, status, message))

        return finish

    def current(self, lesson_id: uuid.UUID | None = None) -> list[LiveCall]:
        calls = [c for c in self._calls.values() if lesson_id is None or c.lesson_id == lesson_id]
        return sorted(calls, key=lambda c: c.started_at)

    def done(self, lesson_id: uuid.UUID) -> list[DoneCall]:
        return list(self._done.get(lesson_id, []))

    def forget(self, lesson_id: uuid.UUID) -> None:
        self._done.pop(lesson_id, None)


LIVE = LiveCalls(lambda: clock.now())  # clock.now remplaçable dans les tests
