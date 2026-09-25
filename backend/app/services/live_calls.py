"""Appels à l'IA en cours dans ce serveur (mémoire du processus), pour la page /suivi."""

import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app import clock


@dataclass(frozen=True)
class LiveCall:
    lesson_id: uuid.UUID | None
    stage: str
    model: str
    started_at: datetime


class LiveCalls:
    """Appels à l'IA en cours dans ce serveur (mémoire du processus)."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._calls: dict[int, LiveCall] = {}
        self._ids = itertools.count()

    def track(self, lesson_id: uuid.UUID | None, stage: str, model: str) -> Callable[[], None]:
        key = next(self._ids)
        self._calls[key] = LiveCall(lesson_id, stage, model, self._now())

        def finish() -> None:
            self._calls.pop(key, None)

        return finish

    def current(self) -> list[LiveCall]:
        return sorted(self._calls.values(), key=lambda c: c.started_at)


LIVE = LiveCalls(lambda: clock.now())  # clock.now remplaçable dans les tests
