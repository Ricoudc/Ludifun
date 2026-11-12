"""§5.54 : le jeu du jour arrive dans la séance avec son nom, et sa raison pour le parent."""

from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.domain.composer import DAILY_GAMES
from tests.api.helpers import auth
from tests.api.test_skills import fractions_lesson


async def test_the_session_names_its_daily_game(client: AsyncClient, fake_llm: FakeProvider) -> None:
    family, lesson = await fractions_lesson(client, fake_llm)
    r = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(family["device"]))
    assert r.status_code in (200, 201), r.text
    named = [i for i in r.json()["items"] if i["daily"] is not None]
    # Leçon de fractions : droite graduée, fractions à colorier… il y a toujours un jeu du jour.
    assert len(named) == 1
    assert named[0]["daily"] in DAILY_GAMES.values()
    assert named[0]["block"] in ("warmup", "core")
    assert all("daily" in i for i in r.json()["items"])
