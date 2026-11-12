"""Programme de la classe (§105) : le parent voit où se rangent les notions des leçons de
l'enfant, ce qui est commencé, maîtrisé ou pas encore vu ; un autre parent ne voit rien."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db.models import KnowledgeItem, KnowledgeMastery
from tests.api.helpers import auth, family_with_device, upload_lesson


async def test_the_parent_sees_the_programme_of_the_grade(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    url = f"/v1/children/{family['child']['id']}/programme"
    parent = auth(family["parent"])
    empty = (await client.get(url, headers=parent)).json()
    assert empty["grade"] == family["child"]["grade"] and empty["version"] and empty["source"]
    history = next(s for s in empty["subjects"] if s["subject"] == "history")
    assert history["started"] == history["mastered"] == 0 and history["total"] >= 3

    lesson = await upload_lesson(client, family["device"])  # La Révolution française (CM1)
    seen = (await client.get(url, headers=parent)).json()
    history = next(s for s in seen["subjects"] if s["subject"] == "history")
    subs = {s["id"]: s for d in history["domains"] for c in d["competences"] for s in c["subs"]}
    revolution = subs["HI-05"]
    assert revolution["title"] == "Le temps de la Révolution et de l'Empire"
    assert revolution["status"] == "started" and history["started"] >= 1
    assert all(n["lesson_id"] == lesson["id"] for n in revolution["notions"])
    assert {n["level"]["value"] for n in revolution["notions"]} == {0}  # pas encore travaillées
    math = next(s for s in seen["subjects"] if s["subject"] == "math")
    assert math["started"] == 0  # rien en maths : tout reste à voir

    # Toutes les notions de la sous-compétence maîtrisées : elle l'est.
    labels = {n["label"] for n in revolution["notions"]}
    items = list(await db.scalars(select(KnowledgeItem).where(KnowledgeItem.label.in_(labels))))
    now = clock.now()
    for item in items:
        db.add(
            KnowledgeMastery(
                child_id=family["child"]["id"],
                knowledge_id=item.id,
                score=95,
                box=5,
                next_review_at=now + timedelta(days=14),
                last_practiced_at=now,
                sessions_count=4,
                levels=[1, 2, 3, 4, 5],
            )
        )
        await db.execute(update(KnowledgeItem).where(KnowledgeItem.id == item.id).values(required_levels=[1]))
    await db.commit()
    done = (await client.get(url, headers=parent)).json()
    history = next(s for s in done["subjects"] if s["subject"] == "history")
    revolution = next(
        s for d in history["domains"] for c in d["competences"] for s in c["subs"] if s["id"] == "HI-05"
    )
    assert revolution["status"] == "mastered" and history["mastered"] >= 1

    other = await family_with_device(client, "autre@example.fr")
    assert (await client.get(url, headers=auth(other["parent"]))).status_code == 404
