"""Critère de fin de l'étape 15 : une leçon collée est analysée sans photo ; une photo avec un mot
illisible demande une vérification avant l'analyse, qui reprend sur le texte corrigé."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import DEMO_LESSON, FakeProvider, LessonScript
from app.ai.schemas import OcrPage, OcrResult, UncertainOut
from app.db.models import AiRun, LessonPage, LessonReviewItem
from tests.api.helpers import auth, family_with_device, upload_lesson

HISTORY = LessonScript.from_file(DEMO_LESSON).ocr_text
BASTILLE = "le peuple de Paris prend la Bastille, une prison"
VERSAILLES = "le 5 mai 1789 à Versailles"


async def test_pasted_lesson_is_analysed_without_a_photo(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    token = (await family_with_device(client))["device"]
    r = await client.post("/v1/lessons/text", json={"text": f"  {HISTORY}  "}, headers=auth(token))
    assert r.status_code == 202, r.text
    lesson = (await client.get(f"/v1/lessons/{r.json()['id']}", headers=auth(token))).json()
    assert lesson["status"] == "ready" and lesson["source"] == "text"
    assert lesson["title"] == "La Révolution française" and lesson["review"] == []
    assert [stage for stage, _ in fake_llm.calls] == ["analysis", "material", "material"]
    assert (await db.scalar(select(LessonPage.ocr_text))) == HISTORY  # relançable, exportable

    short = await client.post("/v1/lessons/text", json={"text": "Les fractions."}, headers=auth(token))
    assert short.status_code == 422 and short.json()["error"]["code"] == "text_too_short"
    long = await client.post("/v1/lessons/text", json={"text": "mot " * 6000}, headers=auth(token))
    assert long.status_code == 422 and long.json()["error"]["code"] == "too_long"


def blurry_photo(fake_llm: FakeProvider) -> None:
    """La lecture hésite sur « Bastille » (lue « Bastile ») et ne lit pas « Versailles »."""
    text = HISTORY.replace("Bastille", "Bastile").replace("à Versailles", "à [illisible]")
    fake_llm.overrides["ocr"] = OcrResult(
        pages=[
            OcrPage(
                index=0,
                quality="partial",
                text=text,
                uncertain=[
                    UncertainOut(text="Bastile", context=BASTILLE.replace("Bastille", "Bastile")),
                    UncertainOut(text="[illisible]", context=VERSAILLES.replace("Versailles", "[illisible]")),
                    UncertainOut(text="Napoléon", context="Napoléon devient empereur"),  # inventé : écarté
                ],
            )
        ],
        language="fr",
        warnings=[],
    )


async def awaiting_review(client: AsyncClient, fake_llm: FakeProvider) -> tuple[str, dict[str, Any]]:
    blurry_photo(fake_llm)
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    return token, lesson


async def test_photo_with_doubtful_words_waits_for_the_child(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    token, lesson = await awaiting_review(client, fake_llm)
    assert lesson["status"] == "needs_review" and lesson["source"] == "photo"
    assert lesson["steps"] == {"reading": "done", "analyzing": "pending", "generating": "pending"}
    assert [(i["read_text"], i["context"]) for i in lesson["review"]] == [
        ("Bastile", "le peuple de Paris prend la Bastile, une prison"),
        ("[illisible]", "le 5 mai 1789 à [illisible]"),
    ]
    assert [stage for stage, _ in fake_llm.calls] == ["ocr"]  # pas d'analyse d'un texte douteux
    summary = (await client.get("/v1/lessons", headers=auth(token))).json()[0]
    assert summary["status"] == "needs_review"

    bastile, unreadable = (i["id"] for i in lesson["review"])
    url = f"/v1/lessons/{lesson['id']}/review"
    missing = await client.post(
        url, json={"answers": [{"item_id": bastile, "status": "confirmed"}]}, headers=auth(token)
    )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "review_incomplete"
    empty = await client.post(
        url,
        json={
            "answers": [
                {"item_id": bastile, "status": "corrected", "text": " "},
                {"item_id": unreadable, "status": "unknown"},
            ]
        },
        headers=auth(token),
    )
    assert empty.status_code == 422

    r = await client.post(
        url,
        json={
            "answers": [
                {"item_id": bastile, "status": "corrected", "text": "Bastille"},
                {"item_id": unreadable, "status": "corrected", "text": "Versailles"},
            ]
        },
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    ready = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).json()
    # Le texte corrigé est exactement celui de la leçon : l'analyse la reconnaît.
    assert ready["status"] == "ready" and ready["title"] == "La Révolution française"
    assert (await db.scalar(select(LessonPage.ocr_text))) == HISTORY
    assert [stage for stage, _ in fake_llm.calls][:2] == ["ocr", "analysis"]
    assert await db.scalar(select(LessonReviewItem.id)) is None  # relecture terminée
    assert {run.stage for run in await db.scalars(select(AiRun))} >= {"ocr", "analysis", "material"}

    again = await client.post(url, json={"answers": []}, headers=auth(token))
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_awaiting_review"


@pytest.mark.parametrize("status", ["confirmed", "unknown"])
async def test_keeping_the_reading_as_is(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider, status: str
) -> None:
    token, lesson = await awaiting_review(client, fake_llm)
    answers = [{"item_id": i["id"], "status": status} for i in lesson["review"]]
    r = await client.post(
        f"/v1/lessons/{lesson['id']}/review", json={"answers": answers}, headers=auth(token)
    )
    assert r.status_code == 202
    text = await db.scalar(select(LessonPage.ocr_text))
    assert text is not None and "Bastile" in text and "[illisible]" in text
    # Le texte n'est plus celui d'une leçon connue de l'IA factice : « pas une leçon ».
    done = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).json()
    assert done["status"] == "failed" and done["failure_reason"] == "not_a_lesson"


async def test_review_belongs_to_the_child(client: AsyncClient, fake_llm: FakeProvider) -> None:
    _, lesson = await awaiting_review(client, fake_llm)
    other = (await family_with_device(client, "autre@example.fr"))["device"]
    answers = [{"item_id": i["id"], "status": "confirmed"} for i in lesson["review"]]
    r = await client.post(
        f"/v1/lessons/{lesson['id']}/review", json={"answers": answers}, headers=auth(other)
    )
    assert r.status_code == 404
