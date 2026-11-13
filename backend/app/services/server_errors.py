"""Erreurs inattendues du serveur (§5.95), gardées en mémoire pour la page /suivi.

Données techniques seulement : l'heure, la méthode, le chemin (identifiants remplacés par
« {id} ») et le type de l'erreur. Ni paramètre, ni corps de requête, ni message : un message
d'erreur peut citer une valeur venue de l'enfant. Les 50 dernières, depuis le démarrage.
"""

import re
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app import clock

KEPT = 50
_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\b\d{3,}\b")


@dataclass(frozen=True)
class ServerError:
    at: datetime
    method: str
    path: str
    kind: str


def route_of(path: str) -> str:
    return _ID.sub("{id}", path.split("?", 1)[0])[:200]


class ServerErrors:
    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._errors: deque[ServerError] = deque(maxlen=KEPT)
        self.since = now()

    def record(self, method: str, path: str, exc: BaseException) -> None:
        self._errors.append(ServerError(self._now(), method, route_of(path), type(exc).__name__))

    def recent(self) -> list[ServerError]:
        return list(reversed(self._errors))

    def by_route(self) -> list[tuple[str, int]]:
        counts = Counter(f"{e.method} {e.path} · {e.kind}" for e in self._errors)
        return counts.most_common()

    def clear(self) -> None:
        self._errors.clear()


ERRORS = ServerErrors(lambda: clock.now())
