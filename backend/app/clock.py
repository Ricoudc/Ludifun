"""Heure courante (UTC), remplaçable dans les tests."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
