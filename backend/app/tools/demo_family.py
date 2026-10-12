"""Crée une famille de démonstration, avec quatre semaines de révisions (développement uniquement).

    uv run python -m app.tools.demo_family
    uv run python -m app.tools.demo_family --email parent.demo@example.fr --replace

Le compte parent contient :
- Emma (CM1), dont la tablette de démonstration a révisé trois leçons de référence (histoire,
  mathématiques, sciences) pendant quatre semaines, avec des erreurs qui se corrigent peu à peu ;
- Hugo (CE1), sans appareil ni séance, pour voir un profil vide.

L'outil affiche l'e-mail, le mot de passe et un code pour lier un vrai téléphone au profil d'Emma.
Les leçons sont analysées par l'IA factice (aucun appel payant) et les séances sont jouées par
l'API elle-même, sur une horloge simulée : le tableau de bord montre donc de vraies données.
Refusé en production.
"""

import argparse
import asyncio
import logging
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import clock
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from app.api.deps import AiProviders
from app.config import Settings, get_settings
from app.db.base import Database
from app.db.models import KnowledgeItem, SessionItem
from app.domain.simulated_pupil import Knows, respond
from app.main import create_app
from app.services.learning import activity_of

DEFAULT_EMAIL = "parent.demo@example.fr"
DEFAULT_PASSWORD = "demo-ludifun-2026"
PHOTO = b"\xff\xd8\xff\xe0" + b"photo de demonstration" * 10
ANSWER_MS = 12_000


class DemoError(Exception):
    pass


@dataclass(frozen=True)
class DemoFamily:
    email: str
    password: str
    emma_id: str
    hugo_id: str
    sessions: int
    link_code: str


@dataclass(frozen=True)
class Revision:
    """Une séance d'Emma : `days_ago` jours avant aujourd'hui, à `hour` heures (heure de Paris)."""

    days_ago: int
    hour: int
    lesson: str
    knows: Knows


def everything(_: str) -> bool:
    return True


def all_but(*keys: str) -> Knows:
    return lambda key: key not in keys


def only(*keys: str) -> Knows:
    return lambda key: key in keys


# Quatre semaines : la Révolution d'abord, puis les fractions (difficiles au début), puis l'eau.
PLAN = [
    Revision(22, 17, "history_cm1_revolution", all_but("k3", "k5", "k6")),
    Revision(16, 17, "history_cm1_revolution", all_but("k3")),
    Revision(16, 18, "math_cm2_fractions", only("k1")),
    Revision(9, 18, "math_cm2_fractions", only("k1", "k2")),
    Revision(9, 18, "history_cm1_revolution", everything),
    Revision(2, 17, "math_cm2_fractions", all_but("k4")),
    Revision(1, 17, "science_ce2_water_states", all_but("k2")),
    Revision(0, 8, "math_cm2_fractions", everything),
]


@contextmanager
def simulated_clock(start: datetime) -> Iterator[list[datetime]]:
    """Remplace l'horloge de l'application le temps de la démonstration."""
    current = [start]
    real = clock.now
    clock.now = lambda: current[0]
    try:
        yield current
    finally:
        clock.now = real


def local(day: date, hour: int, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=tz).astimezone(UTC)


async def create_demo_family(
    client: AsyncClient,
    database: Database,
    llm: FakeProvider,
    *,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    replace: bool = False,
    today: date | None = None,
    tz: ZoneInfo | None = None,
) -> DemoFamily:
    """Joue toute la démonstration à travers l'API (`client`), avec l'IA factice `llm`."""
    tz = tz or ZoneInfo("Europe/Paris")
    today = today or datetime.now(tz).date()

    async def call(method: str, url: str, token: str | None = None, **kwargs: Any) -> Any:
        headers = {"authorization": f"Bearer {token}"} if token else {}
        r = await client.request(method, url, headers=headers, **kwargs)
        if r.status_code >= 400:
            raise DemoError(f"{method} {url} → {r.status_code} {r.text}")
        return r.json() if r.content else None

    existing = await client.post("/v1/auth/login", json={"email": email, "password": password})
    if existing.status_code == 200:
        if not replace:
            raise DemoError(f"Le compte {email} existe déjà : relancez avec --replace pour le recréer.")
        await call("DELETE", "/v1/parent", existing.json()["access_token"])

    # Compte, profils et tablette à l'heure réelle : les jetons doivent être valables maintenant.
    registered = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": password, "accepted_privacy_policy": True},
    )
    if registered.status_code == 409:
        raise DemoError(
            f"Un compte {email} existe déjà avec un autre mot de passe : "
            "choisissez une autre adresse (--email) ou indiquez son mot de passe (--password)."
        )
    if registered.status_code != 201:
        raise DemoError(f"inscription impossible : {registered.status_code} {registered.text}")
    parent = registered.json()["access_token"]
    profile = {"parental_consent": True}
    emma = await call(
        "POST",
        "/v1/children",
        parent,
        json={**profile, "display_name": "Emma", "grade": "CM1", "avatar": "🦊"},
    )
    hugo = await call(
        "POST",
        "/v1/children",
        parent,
        json={**profile, "display_name": "Hugo", "grade": "CE1", "avatar": "🐼"},
    )
    code = (await call("POST", f"/v1/children/{emma['id']}/link-codes", parent))["code"]
    tablet = (
        await call("POST", "/v1/link", json={"code": code, "device_name": "Tablette de démonstration"})
    )["token"]

    # Leçons et séances sur l'horloge simulée.
    scripts = {path.stem: LessonScript.from_file(path) for path in REFERENCE_LESSONS.glob("*.json")}
    lessons: dict[str, str] = {}
    sessions = 0
    # Une séance prévue « aujourd'hui à 8 h » ne doit pas être dans le futur si l'outil tourne plus tôt.
    latest = datetime.now(UTC) - timedelta(minutes=30)
    with simulated_clock(datetime.now(UTC)) as now:
        for revision in PLAN:
            now[0] = min(local(today - timedelta(days=revision.days_ago), revision.hour, tz), latest)
            if revision.lesson not in lessons:
                llm.script = scripts[revision.lesson]
                files = [("pages", ("page1.jpg", PHOTO, "image/jpeg"))]
                lesson = await call("POST", "/v1/lessons", tablet, files=files)
                lessons[revision.lesson] = lesson["id"]
                ready = await call("GET", f"/v1/lessons/{lesson['id']}", tablet)
                if ready["status"] != "ready":
                    raise DemoError(f"leçon {revision.lesson} non analysée : {ready['status']}")
                now[0] += timedelta(minutes=2)
            await _revise(call, database, tablet, lessons[revision.lesson], revision.knows, now)
            sessions += 1

    # Nouveau code (10 minutes) pour lier un vrai téléphone au profil d'Emma.
    link_code = (await call("POST", f"/v1/children/{emma['id']}/link-codes", parent))["code"]
    return DemoFamily(email, password, emma["id"], hugo["id"], sessions, link_code)


async def _revise(
    call: Callable[..., Any],
    database: Database,
    tablet: str,
    lesson_id: str,
    knows: Knows,
    now: list[datetime],
) -> None:
    """Une séance complète jouée par l'élève simulé, reprise des erreurs comprise."""
    session = await call("POST", f"/v1/lessons/{lesson_id}/sessions", tablet, json={})
    async with database.sessionmaker() as db:
        keys = {row.id: row.key for row in await db.scalars(select(KnowledgeItem))}

        async def play(items: list[dict[str, Any]]) -> None:
            queue = list(items)  # + la remédiation insérée en cours de route
            while queue:
                item = queue.pop(0)
                row = await db.get(SessionItem, uuid.UUID(item["id"]))
                assert row is not None
                now[0] += timedelta(milliseconds=ANSWER_MS + 8_000)
                feedback = await call(
                    "POST",
                    f"/v1/sessions/{session['id']}/attempts",
                    tablet,
                    json={
                        "item_id": item["id"],
                        "response": respond(activity_of(row, keys), knows),
                        "duration_ms": ANSWER_MS,
                    },
                )
                queue = feedback["inserted_items"] + queue

        await play(session["items"])
        await play((await call("POST", f"/v1/sessions/{session['id']}/replay", tablet))["items"])
    await call("POST", f"/v1/sessions/{session['id']}/complete", tablet)


async def run(settings: Settings, email: str, password: str, replace: bool) -> DemoFamily:
    llm = FakeProvider()
    app = create_app(settings, ai=AiProviders(VisionLLMOcr(llm), llm))
    logging.getLogger("httpx").setLevel(logging.WARNING)  # seul le résumé final est affiché
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://demo") as client,
    ):
        return await create_demo_family(
            client,
            app.state.database,
            llm,
            email=email,
            password=password,
            replace=replace,
            tz=ZoneInfo(settings.family_timezone),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="au moins 12 caractères")
    parser.add_argument("--replace", action="store_true", help="supprime puis recrée le compte s'il existe")
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.environment == "prod":
        print("Refusé : la famille de démonstration n'est pas faite pour la production.", file=sys.stderr)
        return 2
    try:
        family = asyncio.run(run(settings, args.email, args.password, args.replace))
    except DemoError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(
        f"Famille de démonstration prête : {family.sessions} séances d'Emma sur quatre semaines.\n\n"
        f"  Espace parent : {family.email} / {family.password}\n"
        f"  Code pour lier un téléphone au profil d'Emma : {family.link_code} (valable 10 minutes)\n"
        f"  Hugo : profil vide, sans appareil.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
