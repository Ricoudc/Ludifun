"""Étape 30 : ressources des sites de confiance (MathALÉA, Vikidia, Lumni), cherchées après
l'analyse si le parent l'a permis ; l'enfant les ouvre dans l'application et envoie son score ;
le parent les voit toutes et peut en masquer. Les sites sont simulés : aucun appel à Internet."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from app.config import Settings
from app.db.models import KnowledgeMaterial, LessonResource
from app.services import external_resources, sourced_help, sourced_practice
from app.services.web_sources import WebSources
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.domain.test_resources import REFERENTIAL

SEARX = "http://recherche:8080"
QUIZ = """Teste-toi sur les fractions.
<quiz display=simple>
{Dans une fraction, comment s'appelle le nombre écrit sous le trait ?
|type="()"}
+ Le dénominateur
- Le quotient
- Le diviseur
- Le reste
</quiz>
"""
LUMNI = [
    {"url": "https://www.lumni.fr/video/les-fractions", "title": "Les fractions - Lumni | Primaire"},
    {"url": "https://www.lumni.fr/recherche?q=fractions", "title": "Recherche - Lumni"},
]
# Les Fondamentaux, Maître Lucas : ajoutés aux réponses du moteur dans un seul test.
OTHERS: list[dict[str, str]] = []
sent: list[httpx.Request] = []


def internet(request: httpx.Request) -> httpx.Response:
    sent.append(request)
    if request.url.host == "raw.githubusercontent.com":
        return httpx.Response(200, json=REFERENTIAL)
    if request.url.host == "fr.vikidia.org":
        if request.url.params.get("action") == "query":
            return httpx.Response(200, json={"query": {"search": [{"title": "Fraction"}]}})
        return httpx.Response(200, json={"parse": {"title": "Fraction", "wikitext": QUIZ}})
    if request.url.host == "recherche":
        return httpx.Response(200, json={"results": LUMNI + OTHERS})
    return httpx.Response(404)


@pytest.fixture
def fake_llm() -> FakeProvider:
    return FakeProvider(LessonScript.from_file(REFERENCE_LESSONS / "math_cm2_fractions.json"))


@pytest.fixture
def trusted_sites(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"resources": True, "web_search_url": SEARX})
    sent.clear()
    external_resources.forget_catalogue()

    def fake_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(internet))

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        return WebSources(url, sites, client=fake_client(), library=library)

    monkeypatch.setattr(external_resources, "new_client", fake_client)
    for module in (external_resources, sourced_help, sourced_practice):
        monkeypatch.setattr(module, "WebSources", fake_web)


def resources_url(family: dict[str, Any], lesson: dict[str, Any]) -> str:
    return f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/resources"


async def test_without_the_parent_nothing_is_searched(client: AsyncClient, trusted_sites: None) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["resources"] == []
    assert not [r for r in sent if r.url.host != "recherche"]
    listed = (await client.get(resources_url(family, lesson), headers=auth(family["parent"]))).json()
    assert listed == {"available": False, "resources": []}
    r = await client.post(resources_url(family, lesson) + "/prepare", headers=auth(family["parent"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "resources_not_allowed"


async def test_resources_are_found_opened_and_scored(
    client: AsyncClient, db: AsyncSession, trusted_sites: None
) -> None:
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])

    # MathALÉA : l'exercice noté de la classe ; Vikidia : le quiz ; Lumni : la vidéo seulement.
    by_provider = {r["provider"]: r for r in lesson["resources"]}
    assert set(by_provider) == {"mathalea", "vikidia", "lumni"}
    mathalea = by_provider["mathalea"]
    assert mathalea["kind"] == "exercise" and mathalea["title"] == "Opérations simples avec des fractions"
    assert mathalea["url"].startswith("https://coopmaths.fr/alea/?uuid=f0f0f") and mathalea["best"] is None
    assert "AGPL" in mathalea["licence"] or "Coopmaths" in mathalea["licence"]
    assert by_provider["vikidia"]["url"] == "https://fr.vikidia.org/wiki/Fraction"
    assert by_provider["lumni"] == {**by_provider["lumni"], "kind": "video", "title": "Les fractions"}
    # Seuls le titre et les notions partent vers les sites, jamais le prénom de l'enfant.
    assert not [r for r in sent if "Emma" in str(r.url) or b"Emma" in r.content]

    # La question du quiz rejoint le matériel, avec sa source et sa licence.
    quiz = [
        q
        for m in await db.scalars(select(KnowledgeMaterial))
        for q in m.material.get("questions", [])
        if (q.get("source") or {}).get("site") == "fr.vikidia.org"
    ]
    assert [q["answer"] for q in quiz] == ["Le dénominateur"]
    assert quiz[0]["source"]["licence"] and "Fraction" in quiz[0]["source"]["quote"]

    # L'enfant envoie son score ; le meilleur est gardé.
    result = f"/v1/lessons/{lesson['id']}/resources/{mathalea['id']}/result"
    for correct in (3, 2):
        r = await client.post(result, json={"correct": correct, "total": 5}, headers=auth(family["device"]))
        assert r.status_code == 200, r.text
    assert r.json()["best"] == {"correct": 3, "total": 5}
    bad = await client.post(result, json={"correct": 6, "total": 5}, headers=auth(family["device"]))
    assert bad.status_code == 422

    # Le parent voit tout, avec les essais ; il masque une ressource : l'enfant ne la voit plus.
    parent = auth(family["parent"])
    listed = (await client.get(resources_url(family, lesson), headers=parent)).json()
    assert listed["available"] is True
    seen = next(r for r in listed["resources"] if r["id"] == mathalea["id"])
    assert seen["attempts"] == 2 and seen["hidden"] is False and seen["last_done_at"]
    hidden = await client.post(resources_url(family, lesson) + f"/{mathalea['id']}/hide", headers=parent)
    assert hidden.status_code == 200 and hidden.json()["hidden"] is True
    child_view = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(family["device"]))).json()
    assert mathalea["id"] not in [r["id"] for r in child_view["resources"]]
    r = await client.post(result, json={"correct": 5, "total": 5}, headers=auth(family["device"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "resource_not_found"
    await client.post(resources_url(family, lesson) + f"/{mathalea['id']}/show", headers=parent)
    child_view = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(family["device"]))).json()
    assert mathalea["id"] in [r["id"] for r in child_view["resources"]]

    # Chercher de nouveau : rien n'est dupliqué, le score et le choix du parent restent.
    r = await client.post(resources_url(family, lesson) + "/prepare", headers=parent)
    assert r.status_code == 202, r.text
    rows = list(await db.scalars(select(LessonResource).where(LessonResource.lesson_id == lesson["id"])))
    assert len(rows) == 3
    assert next(row for row in rows if str(row.id) == mathalea["id"]).best_correct == 3


async def test_an_unreachable_site_brings_nothing(
    client: AsyncClient, trusted_sites: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("injoignable")

    monkeypatch.setattr(
        external_resources,
        "new_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(down)),
    )
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready"
    assert {r["provider"] for r in lesson["resources"]} == {"lumni"}


async def test_another_family_cannot_touch_the_resources(client: AsyncClient, trusted_sites: None) -> None:
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    resource = lesson["resources"][0]["id"]
    other = await family_with_device(client, "autre@example.fr")
    path = resources_url(family, lesson)
    for method, url in (("GET", path), ("POST", f"{path}/{resource}/hide"), ("POST", f"{path}/prepare")):
        r = await client.request(method, url, headers=auth(other["parent"]))
        assert r.status_code == 404, (url, r.text)
    r = await client.post(
        f"/v1/lessons/{lesson['id']}/resources/{resource}/result",
        json={"correct": 1, "total": 1},
        headers=auth(other["device"]),
    )
    assert r.status_code == 404


async def test_two_searches_at_once_add_each_resource_once(
    app: FastAPI, client: AsyncClient, db: AsyncSession, trusted_sites: None
) -> None:
    """Deux appuis rapides sur « Chercher des ressources » : deux recherches en même temps,
    chaque ressource et chaque question de quiz une seule fois, sans erreur."""
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    lesson_id = uuid.UUID(lesson["id"])
    await db.execute(delete(LessonResource))
    await db.commit()
    settings = app.state.settings
    await asyncio.gather(
        *(external_resources.prepare(app.state.database, settings, lesson_id) for _ in range(2))
    )
    rows = list(await db.scalars(select(LessonResource).where(LessonResource.lesson_id == lesson_id)))
    assert sorted(r.provider for r in rows) == ["lumni", "mathalea", "vikidia"]
    quiz = [
        q
        for m in await db.scalars(select(KnowledgeMaterial))
        for q in m.material.get("questions", [])
        if (q.get("source") or {}).get("site") == "fr.vikidia.org"
    ]
    assert len(quiz) == 1


async def test_les_fondamentaux_and_maitre_lucas_are_offered_as_links(
    client: AsyncClient, trusted_sites: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le moteur trouve des pages ; seules celles qui parlent de la leçon sont gardées, sans rien
    copier : l'accueil, la recherche, une autre leçon ou un autre site sont écartés."""
    monkeypatch.setattr(
        "tests.api.test_lesson_resources.OTHERS",
        [
            {
                "url": "https://www.reseau-canope.fr/lesfondamentaux/discipline/mathematiques/fractions/les-fractions.html",
                "title": "Les fractions | Les fondamentaux",
            },
            {"url": "https://www.reseau-canope.fr/lesfondamentaux/accueil.html", "title": "Accueil"},
            {"url": "https://www.reseau-canope.fr/boutique/fractions.html", "title": "Fractions : le livre"},
            {
                "url": "https://www.maitrelucas.fr/fractions-cm2/",
                "title": "Les fractions au CM2 - Maître Lucas",
            },
            {"url": "https://www.maitrelucas.fr/la-conjugaison/", "title": "La conjugaison - Maître Lucas"},
            {"url": "https://www.maitrelucas.fr/?s=fractions", "title": "Fractions - Recherche"},
        ],
    )
    family = await family_with_device(client)
    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    linked = {
        (r["provider"], r["kind"], r["title"])
        for r in lesson["resources"]
        if r["provider"] in {"fondamentaux", "maitrelucas"}
    }
    assert linked == {
        ("fondamentaux", "video", "Les fractions"),
        ("maitrelucas", "lesson", "Les fractions au CM2"),
    }
    licences = {r["provider"]: r["licence"] for r in lesson["resources"]}
    assert "rien n'est copié" in licences["maitrelucas"] and "Canopé" in licences["fondamentaux"]
