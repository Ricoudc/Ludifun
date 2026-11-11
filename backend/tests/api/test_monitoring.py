"""Page /suivi et rapport texte : les appels à l'IA, sans donnée personnelle."""

import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson
from app.services.live_calls import LIVE
from app.services.monitoring import clean_message
from tests.api.helpers import family_with_device, upload_lesson


async def test_page_and_live_calls(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready"

    page = await client.get("/suivi")
    assert page.status_code == 200 and "Suivi de l'IA" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert (await client.get("/suivi/suivi.js")).headers["content-type"].startswith("text/javascript")

    data = (await client.get("/suivi/donnees")).json()
    assert data["running"] == [] and data["server_ai"].startswith("fake")
    (recent,) = data["recent"]
    assert recent["lesson"] == lesson["id"][:8] and recent["state"] == "ready" and recent["status"] == "prête"
    assert [s["status"] for s in recent["steps"]] and all(s["status"] == "ok" for s in recent["steps"])
    assert data["stats"] and data["errors"] == []
    # Coût et qualité des exercices (§5.80) : l'IA factice ne coûte rien ; des chiffres seulement.
    assert recent["cost_usd"] == 0 and data["cost"] == {"week_usd": 0, "lessons": 1, "per_lesson_usd": 0}
    exercises = recent["exercises"]
    assert exercises["notions"] == 8 and exercises["questions"] > 0 and exercises["reports"] == 0
    assert exercises["rejected"] >= 0 and all(s["cost_usd"] == 0 for s in data["stats"])
    assert all(s["fallback_calls"] == 0 and s["fallback_rate_pct"] == 0 for s in data["stats"])

    # Une analyse en cours : l'appel à l'IA et sa durée apparaissent.
    lesson_id = uuid.UUID(lesson["id"])
    await db.execute(update(Lesson).where(Lesson.id == lesson_id).values(status="reading"))
    await db.commit()
    finish = LIVE.track(lesson_id, "ocr", "ollama/qwen2.5vl:7b")
    try:
        running = (await client.get("/suivi/donnees")).json()["running"]
    finally:
        finish("ok", None)
        LIVE.forget(lesson_id)
    assert running[0]["lesson"] == lesson["id"][:8]
    assert running[0]["calls"][0] | {"elapsed_s": 0} == {
        "stage": "lecture de la leçon",
        "model": "ollama/qwen2.5vl:7b",
        "elapsed_s": 0,
    }

    text = (await client.get("/suivi/rapport.txt")).text
    assert "== Analyses en cours ==" in text and lesson["id"][:8] in text
    assert "coût 0.0000 $" in text and "exercices : 8 notion(s)" in text and "par leçon" in text
    assert "Révolution" not in text and "Révolution" not in str(data)  # ni titre ni texte de leçon
    assert "@" not in text  # ni e-mail


async def test_monitoring_can_be_closed(app: FastAPI, client: AsyncClient) -> None:
    app.state.settings = app.state.settings.model_copy(update={"monitoring": False})
    for path in ("/suivi", "/suivi/donnees", "/suivi/rapport.txt"):
        assert (await client.get(path)).status_code == 404


def test_error_messages_drop_lesson_content() -> None:
    message = (
        "réponse hors schéma : 1 validation error [type=missing, "
        "input_value={'texte': 'Louis XVI'}, input_type=dict]"
    )
    assert "Louis" not in clean_message(message) and "input_value=…" in clean_message(message)
    assert len(clean_message("x" * 500)) == 200


def test_cost_uses_public_prices_and_unknown_models_say_so() -> None:
    from app.db.models import AiRun
    from app.services.monitoring import _cost, _rejected

    def run(model: str, stage: str = "material", warnings: list[str] | None = None) -> AiRun:
        return AiRun(
            stage=stage,
            provider="claude",
            model=model,
            prompt_version="v1",
            input_tokens=1_000_000,
            output_tokens=100_000,
            latency_ms=1,
            status="ok",
            warnings=warnings or [],
        )

    assert _cost([run("claude-sonnet-5")]) == 3.0  # 2 $ + 0,1 × 10 $
    assert _cost([run("claude-sonnet-5"), run("modele-inconnu")]) is None
    notes = ["k1.questions[0] : l'énoncé contient la réponse", "taux de rejet du matériel élevé : 40%"]
    assert _rejected([run("fake", warnings=notes), run("fake", stage="analysis", warnings=notes)]) == 1


def test_fallback_monitoring_counts_only_recorded_fallbacks() -> None:
    from app.db.models import AiRun
    from app.services.monitoring import _fallback_calls

    def run(warnings: list[str] | None = None) -> AiRun:
        return AiRun(
            stage="analysis",
            provider="ollama",
            model="ollama/qwen2.5vl:7b",
            prompt_version="v1",
            input_tokens=100,
            output_tokens=50,
            latency_ms=1000,
            status="ok",
            warnings=warnings or [],
        )

    assert _fallback_calls([]) == 0
    assert _fallback_calls([run(), run(["notion écartée : source absente"])]) == 0
    assert _fallback_calls([run(["repli : ollama : indisponible"]), run()]) == 1
    assert _fallback_calls([run(["repli : ollama : indisponible"]), run(["repli : quota dépassé"])]) == 2


def test_monitoring_groups_same_model_by_provider_and_stage() -> None:
    from app.db.models import AiRun
    from app.services.monitoring import _group_runs

    def run(provider: str, stage: str = "analysis") -> AiRun:
        return AiRun(
            stage=stage,
            provider=provider,
            model="shared-model",
            prompt_version="v1",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100,
            status="ok",
            warnings=[],
        )

    grouped = _group_runs([run("ollama"), run("gemini"), run("ollama", "material")])
    assert set(grouped) == {
        ("ollama", "shared-model", "analysis"),
        ("gemini", "shared-model", "analysis"),
        ("ollama", "shared-model", "material"),
    }
    assert all(len(group) == 1 for group in grouped.values())
