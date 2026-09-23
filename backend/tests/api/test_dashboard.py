"""Critère de fin de l'étape 8 : le tableau de bord parent, calculé sur un parcours simulé de
plusieurs semaines (deux matières, une semaine creuse, une séance à minuit passé)."""

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from app.db.models import KnowledgeItem, KnowledgeMastery, Lesson
from app.domain.simulated_pupil import Knows
from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)

PARIS = ZoneInfo("Europe/Paris")
SECONDS_PER_ANSWER = 8 + 8  # 8 s de réponse (play) + 8 s de correction


def paris(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=PARIS).astimezone(UTC)


async def revise(
    client: AsyncClient, db: AsyncSession, token: str, lesson_id: str, knows: Knows
) -> tuple[float, int]:
    """Une séance complète (avec la reprise des erreurs) : note sur 10 et nombre de réponses."""
    r = await client.post(f"/v1/lessons/{lesson_id}/sessions", json={}, headers=auth(token))
    assert r.status_code == 200, r.text
    session = r.json()
    answers = len(await play(client, db, token, session["id"], session["items"], knows))
    replay = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()["items"]
    answers += len(await play(client, db, token, session["id"], replay, knows))
    report = (await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))).json()
    return report["score_on_10"], answers


@pytest.fixture
def scripts() -> dict[str, LessonScript]:
    return {path.stem: LessonScript.from_file(path) for path in REFERENCE_LESSONS.glob("*.json")}


async def test_dashboard_over_several_weeks(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
    fake_llm: FakeProvider,
    scripts: dict[str, LessonScript],
) -> None:
    family = await family_with_device(client)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    scores: dict[date, list[float]] = {}
    answers: Counter[date] = Counter()

    async def week_of_revision(lesson_id: str, knows: Knows, monday: date) -> None:
        score, count = await revise(client, db, token, lesson_id, knows)
        scores.setdefault(monday, []).append(score)
        answers[monday] += count

    # Semaine 1 : la Révolution, sans connaître les États généraux (k3).
    now[0] = paris(2026, 8, 31, 17, 0)
    fake_llm.script = scripts["history_cm1_revolution"]
    history = await upload_lesson(client, token)
    await week_of_revision(history["id"], lambda key: key != "k3", date(2026, 8, 31))

    # Semaine 2 : les fractions, presque rien n'est su.
    now[0] = paris(2026, 9, 9, 17, 0)
    fake_llm.script = scripts["math_cm2_fractions"]
    fractions = await upload_lesson(client, token)
    await week_of_revision(fractions["id"], lambda key: key == "k1", date(2026, 9, 7))

    # Semaine 3 : révision le lundi à 0 h 30 à Paris, soit encore dimanche en UTC.
    now[0] = paris(2026, 9, 14, 0, 30)
    assert now[0].date() == date(2026, 9, 13)
    await week_of_revision(history["id"], lambda _: True, date(2026, 9, 14))

    # Semaine 4 (en cours) : les fractions sont revues et sues ; une leçon de sciences arrive.
    now[0] = paris(2026, 9, 22, 17, 0)
    await week_of_revision(fractions["id"], lambda _: True, date(2026, 9, 21))
    now[0] = paris(2026, 9, 23, 10, 0)
    fake_llm.script = scripts["science_ce2_water_states"]
    await upload_lesson(client, token)

    r = await client.get(f"/v1/children/{child_id}/dashboard", params={"weeks": 5}, headers=auth(parent))
    assert r.status_code == 200, r.text
    board: dict[str, Any] = r.json()

    # Progression semaine par semaine, de la plus ancienne à la semaine en cours.
    mondays = [date(2026, 8, 24), date(2026, 8, 31), date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21)]
    assert [w["week_start"] for w in board["weeks"]] == [d.isoformat() for d in mondays]
    for week, monday in zip(board["weeks"], mondays, strict=True):
        expected_scores = scores.get(monday, [])
        assert week["sessions"] == len(expected_scores)
        assert week["minutes"] == round(answers[monday] * SECONDS_PER_ANSWER / 60)
        expected = round(sum(expected_scores) / len(expected_scores), 1) if expected_scores else None
        assert week["average_score"] == expected
    assert board["weeks"][0] == {
        "week_start": "2026-08-24",
        "sessions": 0,
        "minutes": 0,
        "average_score": None,
    }
    assert board["this_week"] == board["weeks"][-1]
    assert board["this_week"]["minutes"] > 0
    week3, week4 = (w["average_score"] for w in board["weeks"][-2:])
    assert board["trend"] == ("up" if week4 - week3 >= 0.5 else "down" if week3 - week4 >= 0.5 else "stable")
    assert board["lessons_added_this_week"] == 1

    # Activités de la semaine : une par réponse (aucune passée).
    assert sum(board["activities_this_week"].values()) == answers[date(2026, 9, 21)]
    assert set(board["activities_this_week"]) <= {
        "MCQ",
        "TRUE_FALSE",
        "FILL_BLANK",
        "MATCH",
        "SPEED_CHALLENGE",
        "FLASHCARD",
    }

    # Réussite par matière : maîtrise pondérée par l'importance des notions travaillées.
    rows = (
        await db.execute(
            select(Lesson.subject, KnowledgeMastery.score, KnowledgeItem.importance)
            .join(KnowledgeItem, KnowledgeItem.id == KnowledgeMastery.knowledge_id)
            .join(Lesson, Lesson.id == KnowledgeItem.lesson_id)
        )
    ).all()
    expected_subjects = []
    for subject in ("math", "history"):  # ordre des matières du programme ; la science n'est pas travaillée
        mine = [(s, w) for subj, s, w in rows if subj == subject]
        percent = round(sum(s * w for s, w in mine) / sum(w for _, w in mine))
        color = "green" if percent >= 80 else "orange" if percent >= 50 else "red"
        expected_subjects.append(
            {"subject": subject, "mastery": percent, "color": color, "notions": len(mine)}
        )
    assert board["subjects"] == expected_subjects

    # À renforcer : au plus 5 notions sous 80 %, les plus faibles d'abord.
    weak = board["to_strengthen"]
    assert 0 < len(weak) <= 5
    assert all(n["mastery"] < 80 for n in weak)
    assert [n["mastery"] for n in weak] == sorted(n["mastery"] for n in weak)
    assert len(weak) == min(5, sum(1 for _, s, _ in rows if s < 80))
    assert {n["lesson_title"] for n in weak} <= {"La Révolution française", "Les fractions"}
    assert board["reviews_due"] == sum(
        1 for m in await db.scalars(select(KnowledgeMastery)) if m.next_review_at <= now[0]
    )

    # Historique (écran P4) : de la plus récente à la plus ancienne, page par page.
    first = (
        await client.get(f"/v1/children/{child_id}/history", params={"limit": 3}, headers=auth(parent))
    ).json()
    assert [s["lesson_title"] for s in first["sessions"]] == [
        "Les fractions",
        "La Révolution française",
        "Les fractions",
    ]
    assert first["next_before"] == first["sessions"][-1]["started_at"]
    rest = (
        await client.get(
            f"/v1/children/{child_id}/history",
            params={"limit": 3, "before": first["next_before"]},
            headers=auth(parent),
        )
    ).json()
    assert rest["next_before"] is None
    oldest = rest["sessions"]
    assert len(oldest) == 1 and oldest[0]["kind"] == "first" and oldest[0]["subject"] == "history"
    assert oldest[0]["status"] == "completed" and oldest[0]["score_on_10"] == scores[date(2026, 8, 31)][0]
    assert oldest[0]["minutes"] == round(answers[date(2026, 8, 31)] * SECONDS_PER_ANSWER / 60)
    notions = {n["label"]: n["status"] for n in oldest[0]["notions"]}
    assert notions.pop("États généraux") in ("to_review", "not_mastered")
    assert set(notions.values()) == {"mastered"}
    assert oldest[0]["notions"][0]["label"] == "États généraux"  # la plus fragile en tête
    assert first["sessions"][1]["kind"] == "review"


async def test_empty_dashboard(client: AsyncClient) -> None:
    family = await family_with_device(client)
    r = await client.get(f"/v1/children/{family['child']['id']}/dashboard", headers=auth(family["parent"]))
    assert r.status_code == 200, r.text
    board = r.json()
    assert len(board["weeks"]) == 4 and board["trend"] is None
    assert board["this_week"]["sessions"] == 0 and board["this_week"]["average_score"] is None
    assert board["subjects"] == [] and board["to_strengthen"] == [] and board["reviews_due"] == 0
    assert board["timezone"] == "Europe/Paris"
    history = await client.get(
        f"/v1/children/{family['child']['id']}/history", headers=auth(family["parent"])
    )
    assert history.json() == {"sessions": [], "next_before": None}


async def test_dashboard_is_parent_only(client: AsyncClient) -> None:
    family = await family_with_device(client)
    child_id = family["child"]["id"]
    for path in ("dashboard", "history"):
        url = f"/v1/children/{child_id}/{path}"
        device = await client.get(url, headers=auth(family["device"]))
        assert device.status_code == 403, device.text  # l'enfant ne voit pas l'espace parent
        stranger = (await register(client, f"autre-{path}@example.fr"))["access_token"]
        other = await client.get(url, headers=auth(stranger))
        assert other.status_code == 404 and other.json()["error"]["code"] == "child_not_found"
        assert (await client.get(url)).status_code == 401
    too_many = await client.get(
        f"/v1/children/{child_id}/dashboard", params={"weeks": 13}, headers=auth(family["parent"])
    )
    assert too_many.status_code == 422
