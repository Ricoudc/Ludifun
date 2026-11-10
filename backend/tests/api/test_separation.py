"""Séparation stricte (§16.1), vérifiée route par route.

- sans jeton : 401 ;
- appareil d'un enfant sur une route parent : 403 ;
- parent d'une autre famille : 404, comme si l'enfant n'existait pas.
"""

import re
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.api.helpers import add_child, auth, family_with_device, link_device, register, upload_lesson

LESSON = "00000000-0000-4000-8000-000000000001"
EDIT = {"kind": "question", "index": 0, "before": "a", "text": "b"}
PARENT_ROUTES = [
    ("GET", "/v1/parent", None),
    ("GET", "/v1/parent/reminders", None),
    ("DELETE", "/v1/parent", None),
    ("GET", "/v1/children", None),
    ("POST", "/v1/children", {"display_name": "X", "grade": "CP", "parental_consent": True}),
    ("PATCH", "/v1/children/{child}", {"grade": "CE2"}),
    ("DELETE", "/v1/children/{child}", None),
    ("POST", "/v1/children/{child}/link-codes", None),
    ("GET", "/v1/children/{child}/devices", None),
    ("GET", "/v1/children/{child}/help-requests", None),
    ("GET", "/v1/children/{child}/question-reports", None),
    ("GET", "/v1/children/{child}/programme", None),
    ("GET", "/v1/children/{child}/homework", None),
    ("GET", "/v1/children/{child}/teach", None),
    ("GET", "/v1/children/{child}/assistant", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/confirm", None),
    ("POST", "/v1/children/{child}/question-reports/" + LESSON + "/seen", None),
    ("DELETE", "/v1/children/{child}/devices/{device}", None),
    # Image d'une leçon (étape 27) : voir, valider, refuser, refaire.
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/image", None),
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/image/file", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/approve", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/reject", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/redo", {}),
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/file", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/approve", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/reject", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/redo", {}),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/prepare", None),
    # Ressources des sites de confiance (étape 30) : voir, masquer, afficher, chercher.
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/resources", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/" + LESSON + "/hide", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/" + LESSON + "/show", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/prepare", None),
    # Relecture par le parent avant l'enfant (§5.69).
    ("GET", "/v1/parent/review-lessons", None),
    ("PUT", "/v1/parent/review-lessons", {"enabled": True}),
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/content", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/approve", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/trial", None),
    (
        "POST",
        "/v1/children/{child}/lessons/" + LESSON + "/trial/check",
        {"seed": "1", "plan": "x", "position": 1, "response": {}},
    ),
    (
        "PUT",
        "/v1/children/{child}/lessons/" + LESSON + "/info",
        {"title": "T", "objective": "O", "summary": "S"},
    ),
    (
        "PUT",
        "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/text",
        {"label": "L", "statement": "S"},
    ),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/remove", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/restore", None),
    # Suivi de l'enfant : tableau de bord, historique, erreurs, compétences, export, contrôles.
    ("GET", "/v1/children/{child}/dashboard", None),
    ("GET", "/v1/children/{child}/history", None),
    ("GET", "/v1/children/{child}/mistakes", None),
    ("GET", "/v1/children/{child}/skills", None),
    ("GET", "/v1/children/{child}/export", None),
    ("GET", "/v1/children/{child}/sessions/" + LESSON, None),
    ("GET", "/v1/children/{child}/exams", None),
    (
        "POST",
        "/v1/children/{child}/exams",
        {"title": "Contrôle", "exam_date": "2030-01-01", "lesson_ids": [LESSON]},
    ),
    ("DELETE", "/v1/children/{child}/exams/" + LESSON, None),
    # Questions d'une notion : corriger à la main, faire refaire par l'IA.
    ("PUT", "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/material", EDIT),
    (
        "POST",
        "/v1/children/{child}/lessons/" + LESSON + "/notions/" + LESSON + "/rework",
        {"reason": "wrong"},
    ),
    # Compte du parent et IA de la famille.
    ("PATCH", "/v1/parent", {}),
    ("POST", "/v1/parent/verify-email", None),
    ("GET", "/v1/parent/ai", None),
    ("PUT", "/v1/parent/ai", {}),
    ("DELETE", "/v1/parent/ai", None),
    ("DELETE", "/v1/parent/ai/providers/groq", None),
    ("PUT", "/v1/parent/ai/sources", {}),
    ("POST", "/v1/parent/ai/test", {}),
]
CHILD_SPECIFIC = [route for route in PARENT_ROUTES if "{child}" in route[1]]


@pytest.fixture
async def world(client: AsyncClient) -> dict[str, Any]:
    """Deux familles : Emma (famille A, un appareil lié) et Léo (famille B)."""
    a = await register(client, "a@example.fr")
    b = await register(client, "b@example.fr")
    emma = await add_child(client, a["access_token"], "Emma")
    leo = await add_child(client, b["access_token"], "Léo")
    device = await link_device(client, a["access_token"], emma["id"])
    return {"a": a["access_token"], "b": b["access_token"], "emma": emma, "leo": leo, "device": device}


def url(path: str, world: dict[str, Any]) -> str:
    return path.format(child=world["emma"]["id"], device=world["device"]["device_id"])


async def call(client: AsyncClient, method: str, path: str, body: Any, token: str | None) -> Any:
    headers = auth(token) if token else {}
    return await client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("method, path, body", PARENT_ROUTES)
async def test_anonymous_is_rejected(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, None)
    assert r.status_code == 401


@pytest.mark.parametrize("method, path, body", PARENT_ROUTES)
async def test_child_device_cannot_use_parent_routes(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, world["device"]["token"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method, path, body", CHILD_SPECIFIC)
async def test_other_family_sees_nothing(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, world["b"])
    assert r.status_code == 404
    # Rien n'a changé pour la famille A.
    children = (await client.get("/v1/children", headers=auth(world["a"]))).json()
    assert [(c["display_name"], c["grade"], c["devices"]) for c in children] == [("Emma", "CM1", 1)]


async def test_child_space_is_limited_to_its_own_child(client: AsyncClient, world: dict[str, Any]) -> None:
    device = world["device"]["token"]
    own = await client.get("/v1/me", params={"child_id": world["emma"]["id"]}, headers=auth(device))
    other = await client.get("/v1/me", params={"child_id": world["leo"]["id"]}, headers=auth(device))
    assert own.status_code == 200 and other.status_code == 404
    # Un parent ne voit pas l'espace d'un enfant d'une autre famille.
    r = await client.get("/v1/me", params={"child_id": world["emma"]["id"]}, headers=auth(world["b"]))
    assert r.status_code == 404


async def test_a_link_code_only_links_its_own_child(client: AsyncClient, world: dict[str, Any]) -> None:
    code = (
        await client.post(f"/v1/children/{world['leo']['id']}/link-codes", headers=auth(world["b"]))
    ).json()
    linked = (await client.post("/v1/link", json={"code": code["code"]})).json()
    assert linked["child"]["display_name"] == "Léo"
    assert (await client.get("/v1/me", headers=auth(linked["token"]))).json()["id"] == world["leo"]["id"]


# Espace enfant : chaque route qui désigne une leçon, une séance, un devoir ou une conversation.
OBJECT = LESSON  # identifiant quelconque, pour les sous-objets (image, ressource)
CHILD_ROUTES: list[tuple[str, str, dict[str, object] | None]] = [
    ("GET", "/v1/lessons/{lesson}", None),
    ("PATCH", "/v1/lessons/{lesson}", {"grade": "6e"}),
    ("DELETE", "/v1/lessons/{lesson}", None),
    ("GET", "/v1/lessons/{lesson}/image", None),
    ("GET", "/v1/lessons/{lesson}/images/" + OBJECT, None),
    ("POST", "/v1/lessons/{lesson}/resources/" + OBJECT + "/result", {"correct": 1, "total": 2}),
    ("POST", "/v1/lessons/{lesson}/retry", None),
    ("POST", "/v1/lessons/{lesson}/review", {"answers": []}),
    ("POST", "/v1/lessons/{lesson}/sessions", {}),
    ("GET", "/v1/lessons/{lesson}/sheet", None),
    ("POST", "/v1/lessons/{lesson}/teach", {}),
    ("GET", "/v1/sessions/{session}", None),
    ("POST", "/v1/sessions/{session}/attempts", {"item_id": "{item}", "response": {"choice_id": "a"}}),
    ("POST", "/v1/sessions/{session}/complete", None),
    ("POST", "/v1/sessions/{session}/errors-session", None),
    ("POST", "/v1/sessions/{session}/extend", None),
    ("POST", "/v1/sessions/{session}/items/{item}/help", {}),
    ("POST", "/v1/sessions/{session}/items/{item}/report", {"reason": "unclear"}),
    ("POST", "/v1/sessions/{session}/replay", None),
    ("GET", "/v1/homework/{homework}", None),
    ("POST", "/v1/homework/{homework}/attempts", {"text": "12"}),
    ("POST", "/v1/homework/{homework}/next-step", None),
    ("POST", "/v1/homework/{homework}/solution", None),
    ("GET", "/v1/teach/{teach}", None),
    ("POST", "/v1/teach/{teach}/answers", {"text": "Bonjour"}),
]
# Espace enfant sans objet : l'enfant est celui du jeton (ou `child_id` pour un parent).
CHILD_SPACE = [
    ("GET", "/v1/me", None),
    ("GET", "/v1/me/mission", None),
    ("GET", "/v1/me/progress", None),
    ("GET", "/v1/lessons", None),
    ("POST", "/v1/lessons/text", {"text": "La Révolution française commence en 1789."}),
    ("GET", "/v1/homework", None),
    ("POST", "/v1/homework/text", {"text": "Léa a 12 billes. Elle en donne 5. Combien en reste-t-il ?"}),
]
# Sans jeton par nature, ou propres au jeton présenté (pas de donnée d'une autre famille).
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/health/ready"),
    ("GET", "/v1/app/latest"),
    ("GET", "/v1/app/ludifun.apk"),
    ("GET", "/v1/figures/{}"),
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/logout"),
    ("POST", "/v1/auth/password-reset"),
    ("POST", "/v1/auth/password-reset/confirm"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/register"),
    ("POST", "/v1/auth/verify-email"),
    ("POST", "/v1/link"),
}
# Envoi de fichiers (mêmes garde-fous que leurs jumelles en texte) et routes du jeton lui-même.
SAME_SCOPE = {
    ("POST", "/v1/lessons"),
    ("POST", "/v1/lessons/document"),
    ("POST", "/v1/homework"),
    ("POST", "/v1/homework/document"),
    ("POST", "/v1/feedback"),
    ("DELETE", "/v1/me/device"),
}


@pytest.fixture
async def content(client: AsyncClient) -> dict[str, Any]:
    """Emma (famille A) a une leçon, une séance, un devoir et une conversation ; Léo (famille B) rien."""
    emma = await family_with_device(client, "a@example.fr")
    leo = await family_with_device(client, "b@example.fr")
    token = auth(emma["device"])
    lesson = await upload_lesson(client, emma["device"])
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=token)).json()
    homework = (await client.post("/v1/homework/text", json=CHILD_SPACE[-1][2], headers=token)).json()
    teach = (await client.post(f"/v1/lessons/{lesson['id']}/teach", json={}, headers=token)).json()
    ids = {
        "lesson": lesson["id"],
        "session": session["id"],
        "item": session["items"][0]["id"],
        "homework": homework["id"],
        "teach": teach["id"],
    }
    return {"emma": emma, "leo": leo, "ids": ids}


def filled(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        for name, identifier in ids.items():
            value = value.replace("{" + name + "}", identifier)
    elif isinstance(value, dict):
        return {k: filled(v, ids) for k, v in value.items()}
    return value


async def test_a_child_never_reaches_another_childs_objects(
    client: AsyncClient, content: dict[str, Any]
) -> None:
    emma, leo, ids = content["emma"], content["leo"], content["ids"]
    strangers = [
        ("tablette de Léo", leo["device"], {}),
        ("parent de Léo, pour Léo", leo["parent"], {"child_id": leo["child"]["id"]}),
        ("parent de Léo, pour Emma", leo["parent"], {"child_id": emma["child"]["id"]}),
        ("tablette de Léo, pour Emma", leo["device"], {"child_id": emma["child"]["id"]}),
    ]
    for method, path, body in CHILD_ROUTES:
        target = filled(path, ids)
        anonymous = await client.request(method, target, json=filled(body, ids))
        assert anonymous.status_code == 401, (method, path)
        for who, token, params in strangers:
            r = await client.request(
                method, target, json=filled(body, ids), headers=auth(token), params=params
            )
            assert r.status_code == 404, (who, method, path, r.status_code, r.text)
    # Rien n'a bougé chez Emma : sa leçon, sa séance, son devoir et sa conversation sont intacts.
    own = auth(emma["device"])
    lesson = (await client.get(f"/v1/lessons/{ids['lesson']}", headers=own)).json()
    assert lesson["status"] == "ready" and lesson["grade"] != "6e"
    assert (await client.get(f"/v1/sessions/{ids['session']}", headers=own)).json()["status"] == "active"
    for path in (f"/v1/homework/{ids['homework']}", f"/v1/teach/{ids['teach']}"):
        assert (await client.get(path, headers=own)).status_code == 200


async def test_the_child_space_never_serves_another_child(
    client: AsyncClient, content: dict[str, Any]
) -> None:
    emma, leo = content["emma"], content["leo"]
    for method, path, body in CHILD_SPACE:
        assert (await client.request(method, path, json=body)).status_code == 401, path
        for token in (leo["device"], leo["parent"]):  # en désignant Emma : introuvable
            r = await client.request(
                method, path, json=body, headers=auth(token), params={"child_id": emma["child"]["id"]}
            )
            assert r.status_code == 404, (method, path, r.status_code)
    # Ce que voit la tablette de Léo est à Léo : ni la leçon ni le devoir d'Emma.
    assert (await client.get("/v1/lessons", headers=auth(leo["device"]))).json() == []
    homework = (await client.get("/v1/homework", headers=auth(leo["device"]))).json()
    assert content["ids"]["homework"] not in str(homework)
    assert (await client.get("/v1/me", headers=auth(leo["device"]))).json()["id"] == leo["child"]["id"]
    assert len((await client.get("/v1/lessons", headers=auth(emma["device"]))).json()) == 1


def test_every_route_is_in_a_separation_list(app: FastAPI) -> None:
    """Une route nouvelle doit être rangée ici (et donc testée), sinon ce test échoue."""

    def shape(path: str) -> str:
        return re.sub(r"\{[^}]+\}|[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}|(?<=/providers/)\w+", "{}", path)

    listed = {(m, shape(p)) for m, p, _ in PARENT_ROUTES + CHILD_ROUTES + CHILD_SPACE} | PUBLIC | SAME_SCOPE
    served = {
        (method.upper(), shape(path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert served - listed == set(), "routes sans test de séparation"
    assert listed - served == set(), "routes listées qui n'existent plus"
