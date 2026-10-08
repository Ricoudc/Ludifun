"""Étape 29 : avec l'accord du parent, des questions tirées des sites de confiance s'ajoutent au
matériel de la leçon ; le parent les voit à part, avec leur source ; sans accord, rien."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AiRun, KnowledgeMaterial
from app.services import sourced_help, sourced_practice
from app.services.web_sources import WebSources
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sourced_help import PAGE, SEARX, internet


@pytest.fixture
def search_engine(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"web_search_url": SEARX})

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        client = httpx.AsyncClient(transport=httpx.MockTransport(internet))
        return WebSources(url, sites, client=client, library=library)

    monkeypatch.setattr(sourced_help, "WebSources", fake_web)
    monkeypatch.setattr(sourced_practice, "WebSources", fake_web)


def sourced_questions(materials: list[KnowledgeMaterial]) -> list[dict[str, Any]]:
    return [q for m in materials for q in m.material.get("questions", []) if q.get("source")]


async def test_questions_from_trusted_sites_join_the_lesson(
    client: AsyncClient, db: AsyncSession, search_engine: None
) -> None:
    family = await family_with_device(client)
    # Sans l'accord du parent : rien n'est cherché, rien n'est ajouté.
    await upload_lesson(client, family["device"])
    assert await db.scalar(select(AiRun.id).where(AiRun.stage == "practice")) is None

    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    runs = list(
        await db.scalars(select(AiRun).where(AiRun.stage == "practice", AiRun.lesson_id == lesson["id"]))
    )
    assert runs and all(r.prompt_version == "v1" for r in runs)
    materials = list(await db.scalars(select(KnowledgeMaterial)))
    added = sourced_questions(materials)
    # La même question pour plusieurs notions : gardée une seule fois (doublons retirés).
    assert len(added) == 1
    source = added[0]["source"]
    assert source["site"] == "fr.vikidia.org" and source["quote"] in internet_text()
    assert added[0]["answer"] in source["quote"]
    assert any("double" in w for r in runs for w in r.warnings)

    # Le parent les voit à part, avec la phrase qui prouve la réponse.
    content = (
        await client.get(
            f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/content",
            headers=auth(family["parent"]),
        )
    ).json()
    titles = [b["title"] for n in content["notions"] for b in n["blocks"]]
    assert "📚 Questions tirées des sites de confiance" in titles


def internet_text() -> str:
    from tests.api.test_sourced_help import HTML

    return HTML


async def test_a_correction_made_meanwhile_is_never_overwritten(
    app: FastAPI, client: AsyncClient, db: AsyncSession, fake_llm: Any, search_engine: None
) -> None:
    """La recherche tourne plusieurs minutes en fond (Ollama) ; si le parent fait corriger une
    notion pendant ce temps, l'ajout des questions des sites se fait sur la version corrigée."""
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    original = fake_llm.structured
    marker = {
        "difficulty": 1,
        "stem": "Question revue par le parent pendant la recherche ?",
        "answer": "Oui",
        "distractors": ["Non", "Peut-être", "Jamais"],
    }

    corrected = False

    async def parent_meanwhile(*, prompt: Any, **kwargs: Any) -> Any:
        nonlocal corrected
        if prompt.stage == "practice" and not corrected:  # pendant le 1er appel : correction ailleurs
            corrected = True
            async with app.state.database.sessionmaker() as other:
                for row in await other.scalars(select(KnowledgeMaterial)):
                    questions = row.material.get("questions", [])
                    if marker not in questions:
                        row.material = {**row.material, "questions": [*questions, marker]}
                await other.commit()
        return await original(prompt=prompt, **kwargs)

    fake_llm.structured = parent_meanwhile
    await upload_lesson(client, family["device"])
    materials = list(await db.scalars(select(KnowledgeMaterial)))
    assert sourced_questions(materials)  # les questions des sites sont bien ajoutées…
    for row in materials:  # … sans effacer la correction du parent
        assert marker["stem"] in [q["stem"] for q in row.material["questions"]], row.knowledge_id


LUMNI_PAGE = "https://www.lumni.fr/article/la-revolution-francaise"
LUMNI_HTML = (
    "<html><head><title>La Révolution française - Lumni</title></head><body>"
    "<p>En 1789, les députés du tiers état se proclament Assemblée nationale et prêtent le "
    "serment du Jeu de paume pour donner une Constitution à la France.</p></body></html>"
)


def internet_with_lumni(request: httpx.Request) -> httpx.Response:
    if request.url.host == "recherche":
        results = [{"url": PAGE, "title": "Révolution française"}]
        if "lumni" in request.url.params.get("q", ""):
            results.insert(0, {"url": LUMNI_PAGE, "title": "La Révolution française - Lumni"})
        return httpx.Response(200, json={"results": results})
    html = LUMNI_HTML if request.url.host == "www.lumni.fr" else internet_text()
    return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})


async def test_lumni_comes_first_for_the_questions(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les questions s'appuient d'abord sur Lumni (thème de la leçon) ; l'IA écrit ses propres
    questions, chacune prouvée par une phrase citée de la page, avec le lien."""
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"web_search_url": SEARX})

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        client = httpx.AsyncClient(transport=httpx.MockTransport(internet_with_lumni))
        return WebSources(url, sites, client=client, library=library)

    monkeypatch.setattr(sourced_help, "WebSources", fake_web)
    monkeypatch.setattr(sourced_practice, "WebSources", fake_web)
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    await upload_lesson(client, family["device"])
    added = sourced_questions(list(await db.scalars(select(KnowledgeMaterial))))
    lumni = [q for q in added if q["source"]["site"] == "www.lumni.fr"]
    assert lumni, added
    assert lumni[0]["source"]["url"] == LUMNI_PAGE and lumni[0]["source"]["quote"] in LUMNI_HTML
    # Une notion dont la page Lumni ne parle pas : les autres sites prennent le relais.
    assert {q["source"]["site"] for q in added} <= {"www.lumni.fr", "fr.vikidia.org"}
