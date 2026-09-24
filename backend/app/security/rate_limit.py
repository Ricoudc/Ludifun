"""Limitation de débit en mémoire (une instance d'API).

Suffisant pour la V1 et la bêta ; à remplacer par un stockage partagé (Redis)
quand l'API tournera sur plusieurs instances.
"""

import time
from collections import deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window_s: float) -> float | None:
        """Enregistre un essai ; renvoie le délai d'attente en secondes si la limite est dépassée."""
        wait = self.exceeded(key, limit, window_s)
        if wait is None:
            self._hits.setdefault(key, deque()).append(time.monotonic())
        return wait

    def exceeded(self, key: str, limit: int, window_s: float) -> float | None:
        """Comme `hit`, sans enregistrer d'essai."""
        now = time.monotonic()
        hits = self._hits.get(key)
        if hits is None:
            return None
        while hits and hits[0] <= now - window_s:
            hits.popleft()
        if not hits:
            del self._hits[key]  # une clé expirée ne reste pas en mémoire
            return None
        return hits[0] + window_s - now if len(hits) >= limit else None

    def __len__(self) -> int:
        return len(self._hits)

    def purge(self, max_window_s: float) -> None:
        """Oublie les clés sans essai récent (appelé régulièrement : la mémoire reste bornée)."""
        horizon = time.monotonic() - max_window_s
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= horizon]:
            del self._hits[key]

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
