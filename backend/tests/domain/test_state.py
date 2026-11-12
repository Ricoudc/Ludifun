"""État pédagogique d'une notion (CDC §114, §129, §131) : par niveau, autonomie, faits chiffrés."""

from datetime import UTC, datetime, timedelta

from app.domain.state import Observation, facts_sentence, notion_state

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def obs(i: int, level: int, score: float, help_level: int = 0, error: str | None = None) -> Observation:
    result = score * (0.5 if help_level >= 4 else 1.0)
    return Observation(T0 + timedelta(days=i), level, result, score, help_level, error)


def test_state_by_level_and_independence() -> None:
    state = notion_state(
        [
            obs(0, 1, 1),
            obs(1, 1, 1),
            obs(2, 2, 0, error="confusion"),
            obs(3, 2, 1, help_level=4),
            obs(4, 2, 0, error="confusion"),
            obs(5, 3, 0.5),
        ]
    )
    assert state.level_rates == {1: 1.0, 2: round(0.5 / 3, 2), 3: 0.5, 4: None, 5: None}
    assert state.independence == 0.75  # 4 réussies, dont 1 avec une aide
    assert (state.alone, state.helped, state.partial, state.failed) == (2, 1, 1, 2)
    assert facts_sentence(state) == (
        "Sur les 6 dernières activités : 2 réussies seul, 1 avec une aide, 1 à moitié, 2 ratées. "
        "Erreur la plus fréquente : confond avec une autre notion (2 fois)."
    )


def test_only_the_recent_activities_are_told() -> None:
    state = notion_state([obs(i, 1, 0) for i in range(5)] + [obs(10 + i, 1, 1) for i in range(8)])
    assert facts_sentence(state) == "Sur les 8 dernières activités : 8 réussies seul."
    assert state.level_rates[1] == 0.8  # les 10 dernières réponses de ce niveau


def test_nothing_yet() -> None:
    state = notion_state([])
    assert facts_sentence(state) is None and state.independence is None
    assert set(state.level_rates.values()) == {None}
    assert facts_sentence(notion_state([obs(0, 1, 0)])) == "Sur la dernière activité : 1 ratée."
