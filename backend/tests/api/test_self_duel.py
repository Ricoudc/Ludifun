"""§5.98 : duel contre soi. Le bilan rappelle la note de la séance précédente sur la même leçon."""

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.helpers import family_with_device, upload_lesson
from tests.api.test_rewards import revise
from tests.api.test_sessions import now  # noqa: F401  (fixture)


async def test_the_report_recalls_the_previous_score(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)

    first = await revise(client, db, token, lesson["id"], lambda key: key != "k3")
    assert first["previous_score_on_10"] is None  # rien à battre la première fois

    now[0] += timedelta(days=1)
    second = await revise(client, db, token, lesson["id"], lambda _: True)
    assert second["previous_score_on_10"] == first["score_on_10"]
    assert second["score_on_10"] > first["score_on_10"]

    # Une autre leçon a son propre duel.
    other = await upload_lesson(client, token)
    now[0] += timedelta(days=1)
    alone = await revise(client, db, token, other["id"], lambda _: True)
    assert alone["previous_score_on_10"] is None
