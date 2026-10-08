"""Étape 25 : consignes au niveau de la classe de l'enfant, dans la séance et pour l'IA."""

from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.domain.instructions import instruction, writing_rules
from app.domain.text import display_text
from tests.api.helpers import add_child, auth, link_device, register, upload_lesson


async def test_instructions_follow_the_child_grade(client: AsyncClient, fake_llm: FakeProvider) -> None:
    parent = (await register(client))["access_token"]
    for grade in ("CP", "4e"):
        fake_llm.calls.clear()
        child = await add_child(client, parent, name=f"Élève {grade}", grade=grade)
        token = (await link_device(client, parent, child["id"]))["token"]
        lesson = await upload_lesson(client, token)
        # L'IA qui prépare les questions reçoit les règles d'écriture de la classe de l'enfant.
        material_inputs = [text for stage, text in fake_llm.calls if stage == "material"]
        assert material_inputs and all(f"Écriture : {writing_rules(grade)}" in t for t in material_inputs)

        session = (
            await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))
        ).json()
        assert session["items"]
        for item in session["items"]:
            assert item["instruction"] == display_text(instruction(item["type"], grade))
