"""Critère de fin de l'étape 14 : aide 1 → 5 sans voir la réponse avant 5 ; réponse ouverte
corrigée (par l'IA, ou par mots clés si elle manque) ; erreur récurrente signalée au parent."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError
from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from app.db.models import AiRun, AttemptEvidence, KnowledgeItem, KnowledgeMastery, SessionItem
from app.services import ai_budget, answer_evaluation
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)

FRACTIONS = REFERENCE_LESSONS / "math_cm2_fractions.json"


async def start(client: AsyncClient, token: str, lesson_id: str) -> dict[str, Any]:
    r = await client.post(f"/v1/lessons/{lesson_id}/sessions", json={}, headers=auth(token))
    assert r.status_code == 200, r.text
    session: dict[str, Any] = r.json()
    return session


async def fractions(client: AsyncClient, fake_llm: FakeProvider) -> tuple[dict[str, Any], dict[str, Any]]:
    fake_llm.script = LessonScript.from_file(FRACTIONS)
    family = await family_with_device(client)
    return family, await upload_lesson(client, family["device"])


# --------------------------------------------------------------------------- #
# « Je n'ai pas compris »
# --------------------------------------------------------------------------- #


async def test_help_climbs_to_the_answer_then_counts_for_nothing(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson = await fractions(client, fake_llm)
    token = family["device"]
    session = await start(client, token, lesson["id"])
    comparing = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k4"))
    item = next(i for i in session["items"] if i["knowledge_ids"] == [str(comparing)])
    assert item["help_available"] and item["help_level"] == 0
    row = await db.get(SessionItem, uuid.UUID(item["id"]))
    assert row is not None
    answer = row.solution["display"]

    url = f"/v1/sessions/{session['id']}/items/{item['id']}/help"
    steps: list[dict[str, Any]] = []
    while not steps or not steps[-1]["last"]:
        r = await client.post(url, headers=auth(token))
        assert r.status_code == 200, r.text
        steps.append(r.json())
    levels = [s["level"] for s in steps]
    assert levels == sorted(levels) and len(set(levels)) == len(levels) and levels[-1] == 5
    assert steps[0]["kind"] == "hint" and steps[0]["title"] == "💡 Un indice"
    assert all(answer not in " ".join([s["text"], *s["lines"]]) for s in steps[:-1]), (answer, steps)
    assert steps[-1]["kind"] == "answer" and steps[-1]["text"] == answer
    again = (await client.get(f"/v1/sessions/{session['id']}", headers=auth(token))).json()
    assert next(i for i in again["items"] if i["id"] == item["id"])["help_level"] == 5

    # Réussir après avoir vu la réponse : la note ne change pas, la maîtrise ne le compte pas.
    feedback = await play(client, db, token, session["id"], [item], lambda _: True)
    assert feedback[0]["result"] == "correct" and feedback[0]["score"] == 1
    evidence = await db.scalar(select(AttemptEvidence).where(AttemptEvidence.knowledge_id == comparing))
    assert evidence is not None and float(evidence.result) == 0 and evidence.error_type is None

    answered = await client.post(url, headers=auth(token))
    assert answered.status_code == 409 and answered.json()["error"]["code"] == "already_answered"
    match = next(i for i in session["items"] if i["type"] in ("MATCH", "SPEED_CHALLENGE"))
    assert not match["help_available"]
    refused = await client.post(f"/v1/sessions/{session['id']}/items/{match['id']}/help", headers=auth(token))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "help_unavailable"


async def test_error_types_are_recorded(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson = await fractions(client, fake_llm)
    token = family["device"]
    session = await start(client, token, lesson["id"])
    first, second = session["items"][:2]
    wrong = await db.get(SessionItem, uuid.UUID(first["id"]))
    assert wrong is not None and wrong.activity_type in ("MCQ", "TRUE_FALSE")
    response = (
        {
            "choice_id": next(
                c["id"] for c in wrong.payload["choices"] if c["id"] != wrong.solution["choice_id"]
            )
        }
        if wrong.activity_type == "MCQ"
        else {"value": not wrong.solution["value"]}
    )
    for item, duration in ((first, 600), (second, 9000)):
        body = {
            "item_id": item["id"],
            "response": response if item is first else None,
            "duration_ms": duration,
        }
        if item is second:
            row = await db.get(SessionItem, uuid.UUID(second["id"]))
            assert row is not None
            body["response"] = (
                {
                    "choice_id": next(
                        c["id"] for c in row.payload["choices"] if c["id"] != row.solution["choice_id"]
                    )
                }
                if row.activity_type == "MCQ"
                else {"value": not row.solution["value"]}
            )
        r = await client.post(f"/v1/sessions/{session['id']}/attempts", json=body, headers=auth(token))
        assert r.status_code == 200, r.text
    errors = [e.error_type or "" for e in await db.scalars(select(AttemptEvidence))]
    assert sorted(errors) == ["knowledge", "random"]  # la réponse en 0,6 s : au hasard


# --------------------------------------------------------------------------- #
# Questions ouvertes
# --------------------------------------------------------------------------- #


async def open_question_session(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Tout est su sauf la comparaison (k4), maîtrisée à tous les niveaux exigés et due : la
    révision l'approfondit par une question ouverte « explique pourquoi »."""
    family, lesson = await fractions(client, fake_llm)
    token = family["device"]
    child_id = uuid.UUID(family["child"]["id"])
    for item in await db.scalars(select(KnowledgeItem)):
        due = item.key == "k4"
        db.add(
            KnowledgeMastery(
                child_id=child_id,
                knowledge_id=item.id,
                score=85 if due else 95,
                box=3 if due else 5,
                levels=[1, 2, 3],
                next_review_at=now[0] - timedelta(hours=1) if due else now[0] + timedelta(days=10),
                last_practiced_at=now[0] - timedelta(days=4),
            )
        )
    await db.commit()
    session = await start(client, token, lesson["id"])
    item = next(i for i in session["items"] if i["type"] == "OPEN_QUESTION")
    assert item["payload"] == {"prompt": "Explique pourquoi 5/8 est plus grand que 3/8.", "max_length": 600}
    return token, session, item


async def test_open_question_graded_by_the_ai(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    token, session, item = await open_question_session(client, db, fake_llm, now)
    r = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={
            "item_id": item["id"],
            "response": {"text": "Elles ont le même dénominateur."},
            "duration_ms": 30000,
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    correction = r.json()
    assert correction["result"] == "incorrect" and correction["score"] == 0.33
    assert correction["explanation"] == "C'est un début : relis la correction."  # retour de l'évaluateur
    assert [d["found"] for d in correction["details"]] == [True, False, False]
    assert correction["correct_answer"].startswith("Les deux fractions ont le même dénominateur")
    run = await db.scalar(select(AiRun).where(AiRun.stage == "evaluation"))
    assert run is not None and run.status == "ok" and run.lesson_id == uuid.UUID(session["lesson_id"])
    sent = next(text for stage, text in fake_llm.calls if stage == "evaluation")
    assert "<reponse_eleve>\nElles ont le même dénominateur.\n</reponse_eleve>" in sent
    assert "Classe de l'élève : CM2" in sent
    error = await db.scalar(select(AttemptEvidence.error_type))
    assert error == "knowledge"


@pytest.mark.parametrize("failure", ["ai_error", "timeout", "budget"])
async def test_open_question_without_the_ai(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    token, session, item = await open_question_session(client, db, fake_llm, now)
    if failure == "ai_error":
        fake_llm.overrides["evaluation"] = AIError("API 529 : overloaded")
    elif failure == "timeout":  # IA locale lente : l'application n'attend que 30 s
        monkeypatch.setattr(answer_evaluation, "TIMEOUT_S", 0.05)
        scripted = fake_llm.structured

        async def slow(**kwargs: Any) -> Any:
            if kwargs["prompt"].stage == "evaluation":
                await asyncio.sleep(1)
            return await scripted(**kwargs)

        monkeypatch.setattr(fake_llm, "structured", slow)
    else:

        async def exhausted(*_: object) -> int:
            return 3600

        monkeypatch.setattr(ai_budget, "seconds_until_budget", exhausted)
    text = "Même dénominateur : on compare les numérateurs, et 5 est plus grand que 3."
    r = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": item["id"], "response": {"text": text}, "duration_ms": 30000},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "correct"  # corrigée par les mots clés
    runs = list(await db.scalars(select(AiRun).where(AiRun.stage == "evaluation")))
    if failure == "timeout":
        assert runs[0].warnings == ["pas de réponse en 0.05 s"]
    assert [run.status for run in runs] == ([] if failure == "budget" else ["error"])


async def test_open_question_answer_is_bounded(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    token, session, item = await open_question_session(client, db, fake_llm, now)
    r = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": item["id"], "response": {"text": "x" * 601}},
        headers=auth(token),
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_response"
    assert not [stage for stage, _ in fake_llm.calls if stage == "evaluation"]


# --------------------------------------------------------------------------- #
# Erreur récurrente, côté parent
# --------------------------------------------------------------------------- #


async def test_recurring_error_reaches_the_parent(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)  # la Révolution française
    for _ in range(3):  # Emma ne connaît pas les États généraux (k3), trois jours de suite
        now[0] += timedelta(days=1)
        session = await start(client, token, lesson["id"])
        await play(client, db, token, session["id"], session["items"], lambda key: key != "k3")
        await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))

    board = (
        await client.get(f"/v1/children/{family['child']['id']}/dashboard", headers=auth(family["parent"]))
    ).json()
    assert board["error_types"] and board["error_types"][0]["count"] >= 3
    assert all(e["label"] for e in board["error_types"])
    recurring = [r for r in board["recurring_errors"] if r["label"] == "États généraux"]
    assert recurring and all(r["sessions"] == 3 for r in recurring)
    assert all(r["lesson_title"] == "La Révolution française" for r in recurring)
    assert {r["error_label"] for r in recurring} <= {
        "Ne connaît pas encore",
        "Ne s'en souvient pas",
        "Confond avec une autre notion",
        "Presque : une faute ou un détail",
    }
