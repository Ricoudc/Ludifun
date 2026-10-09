import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.base import Base
from app.db.models import (
    AiRun,
    Attempt,
    AttemptEvidence,
    Child,
    Device,
    Family,
    FamilyMember,
    KnowledgeItem,
    KnowledgeMastery,
    KnowledgeMaterial,
    Lesson,
    LessonPage,
    Parent,
    RevisionSession,
    SessionItem,
)
from tests.conftest import run_alembic


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    """Toute modification de app/db/models.py doit avoir sa migration Alembic."""

    def diff(sync_conn: Connection) -> list[Any]:
        context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        differences: list[Any] = compare_metadata(context, Base.metadata)
        return differences

    async with engine.connect() as conn:
        assert await conn.run_sync(diff) == []


async def test_migrations_downgrade_and_upgrade(engine: AsyncEngine) -> None:
    await run_alembic("downgrade", "base")
    await run_alembic("upgrade", "head")


async def create_full_lesson(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Une leçon avec toutes les tables remplies, comme après une vraie séance."""
    now = datetime.now(UTC)
    parent = Parent(email=f"{uuid.uuid4()}@example.fr", password_hash="x", privacy_accepted_at=now)
    family = Family()
    db.add_all([parent, family])
    await db.flush()
    child = Child(family_id=family.id, display_name="Emma", grade="CM1", parental_consent_at=now)
    db.add_all([FamilyMember(family_id=family.id, parent_id=parent.id, role="owner"), child])
    await db.flush()
    db.add(Device(child_id=child.id, token_hash=uuid.uuid4().bytes))
    lesson = Lesson(child_id=child.id, status="ready", page_count=1, subject="history", grade="CM1")
    db.add(lesson)
    await db.flush()
    knowledge = KnowledgeItem(
        lesson_id=lesson.id,
        key="k1",
        type="date",
        label="1789",
        importance=5,
        position=0,
        statement="La Révolution française commence en 1789.",
        source_excerpt="commence en 1789",
    )
    db.add_all([knowledge, LessonPage(lesson_id=lesson.id, page_index=0, ocr_text="…", quality="good")])
    await db.flush()
    session = RevisionSession(
        child_id=child.id,
        lesson_id=lesson.id,
        kind="first",
        status="active",
        objective="Connaître 1789",
        estimated_duration_s=480,
        seed=42,
    )
    db.add_all(
        [
            session,
            KnowledgeMaterial(knowledge_id=knowledge.id, material={"tip": "1789"}, prompt_version="v1"),
            AiRun(
                lesson_id=lesson.id,
                stage="analysis",
                provider="fake",
                model="fake",
                prompt_version="v1",
                latency_ms=10,
                status="ok",
            ),
        ]
    )
    await db.flush()
    item = SessionItem(
        session_id=session.id,
        position=1,
        block="warmup",
        activity_type="MCQ",
        difficulty=1,
        knowledge_ids=[knowledge.id],
        payload={"prompt": "?"},
        solution={"choice_id": "b"},
    )
    db.add(item)
    await db.flush()
    attempt = Attempt(session_item_id=item.id, response={"choice_id": "b"}, score=Decimal("1"))
    db.add(attempt)
    await db.flush()
    db.add_all(
        [
            AttemptEvidence(
                attempt_id=attempt.id, knowledge_id=knowledge.id, result=Decimal("1"), weight=Decimal("0.6")
            ),
            KnowledgeMastery(
                child_id=child.id,
                knowledge_id=knowledge.id,
                score=100,
                box=2,
                next_review_at=now,
                last_practiced_at=now,
            ),
        ]
    )
    await db.commit()
    return {"family": family.id, "parent": parent.id, "lesson": lesson.id, "knowledge": knowledge.id}


async def test_deleting_a_family_erases_all_its_data(db: AsyncSession) -> None:
    """Droit à l'effacement (§16.2) : la suppression du compte parent repose sur ces cascades."""
    ids = await create_full_lesson(db)
    await db.delete(await db.get(Family, ids["family"]))
    await db.delete(await db.get(Parent, ids["parent"]))
    await db.commit()

    for model in Base.metadata.sorted_tables:
        if model.name == "ai_runs":
            continue
        count = (await db.execute(select(func.count()).select_from(model))).scalar_one()
        assert count == 0, f"{model.name} contient encore {count} ligne(s)"

    # Les statistiques de coût IA sont conservées, sans lien vers la leçon supprimée.
    run = (await db.execute(select(AiRun))).scalar_one()
    assert run.lesson_id is None


@pytest.mark.parametrize(
    "field, value",
    [("importance", 6), ("importance", 0), ("type", None)],
)
async def test_knowledge_item_constraints(db: AsyncSession, field: str, value: object) -> None:
    ids = await create_full_lesson(db)
    data = dict(
        lesson_id=ids["lesson"],
        key="k2",
        type="person",
        label="Louis XVI",
        importance=4,
        position=1,
        statement="Louis XVI est roi.",
        source_excerpt="le roi Louis XVI",
    )
    db.add(KnowledgeItem(**{**data, field: value}))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_lesson_status_and_page_count_are_checked(db: AsyncSession) -> None:
    ids = await create_full_lesson(db)
    child_id = (await db.execute(select(Child.id))).scalar_one()
    for bad in ({"status": "done"}, {"page_count": 7}, {"failure_reason": "oops", "status": "failed"}):
        db.add(Lesson(**{"child_id": child_id, "status": "uploaded", "page_count": 1, **bad}))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    assert ids


async def test_migration_0003_fills_levels_from_existing_data(engine: AsyncEngine, db: AsyncSession) -> None:
    """Les séances déjà jouées donnent les niveaux validés ; le matériel, les niveaux exigés."""
    ids = await create_full_lesson(db)  # k1 (date) : un QCM réussi
    lesson, k1 = ids["lesson"], ids["knowledge"]
    session = await db.scalar(select(RevisionSession).where(RevisionSession.lesson_id == lesson))
    assert session is not None
    session.status = "completed"
    material = await db.get(KnowledgeMaterial, k1)
    assert material is not None
    material.material = {"cloze": {"text": "En ___", "answers": ["1789"]}, "questions": []}
    k2 = KnowledgeItem(
        lesson_id=lesson, key="k2", type="rule", label="Règle", importance=4, position=1,
        statement="On compare les numérateurs.", source_excerpt="compare",
    )  # fmt: skip
    db.add(k2)
    await db.flush()
    child_id = await db.scalar(select(KnowledgeMastery.child_id))
    db.add_all(
        [
            KnowledgeMaterial(
                knowledge_id=k2.id,
                material={"questions": [{"difficulty": 3}], "flashcard": {"front": "a", "back": "b"}},
                prompt_version="v1",
            ),
            KnowledgeMastery(
                child_id=child_id,
                knowledge_id=k2.id,
                score=100,
                box=2,
                next_review_at=datetime.now(UTC),
                last_practiced_at=datetime.now(UTC),
            ),
        ]
    )
    answers = [("FILL_BLANK", 2, k1, "0"), ("MCQ", 3, k2.id, "1")]  # texte à trous raté, application réussie
    for position, (activity, difficulty, knowledge, result) in enumerate(answers, start=2):
        item = SessionItem(
            session_id=session.id, position=position, block="core", activity_type=activity,
            difficulty=difficulty, knowledge_ids=[knowledge], payload={}, solution={},
        )  # fmt: skip
        db.add(item)
        await db.flush()
        attempt = Attempt(session_item_id=item.id, response={}, score=Decimal(result))
        db.add(attempt)
        await db.flush()
        db.add(
            AttemptEvidence(
                attempt_id=attempt.id, knowledge_id=knowledge, result=Decimal(result), weight=Decimal("1")
            )
        )
    await db.commit()

    await run_alembic("downgrade", "0002")
    await run_alembic("upgrade", "head")

    async with engine.connect() as conn:
        rows = (await conn.execute(select(KnowledgeItem.key, KnowledgeItem.required_levels))).all()
        required = {key: value for key, value in rows}
        mastery_rows = (
            await conn.execute(select(KnowledgeMastery.knowledge_id, KnowledgeMastery.levels))
        ).all()
        levels = {key: value for key, value in mastery_rows}
        items = (
            await conn.execute(
                select(SessionItem.activity_type, SessionItem.difficulty, SessionItem.cognitive_level)
            )
        ).all()
    assert required == {"k1": [1, 2], "k2": [1, 2, 3]}
    assert levels == {k1: [1], k2.id: [3]}
    assert sorted(items) == [("FILL_BLANK", 2, 2), ("MCQ", 1, 1), ("MCQ", 3, 3)]


async def test_migration_0013_keeps_the_family_ai_setting(engine: AsyncEngine, db: AsyncSession) -> None:
    """Le réglage d'IA d'avant (un seul, clé comprise) devient l'IA active et son réglage."""
    await db.commit()
    await run_alembic("downgrade", "0012")
    async with engine.begin() as conn:
        family_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO families (id, created_at) VALUES (:id, now())"), {"id": family_id}
        )
        await conn.execute(
            text(
                "INSERT INTO family_ai_settings "
                "(family_id, provider, model, base_url, api_key_encrypted, key_hint, updated_at) "
                "VALUES (:id, 'claude', 'claude-sonnet-5', NULL, :key, '…1234', now())"
            ),
            {"id": family_id, "key": b"chiffree"},
        )
    await run_alembic("upgrade", "head")
    async with engine.connect() as conn:
        active = (await conn.execute(text("SELECT provider FROM family_ai_settings"))).all()
        saved = (
            await conn.execute(
                text("SELECT provider, model, api_key_encrypted, key_hint FROM family_ai_providers")
            )
        ).all()
    assert [tuple(row) for row in active] == [("claude",)]
    assert [tuple(row) for row in saved] == [("claude", "claude-sonnet-5", b"chiffree", "…1234")]


async def test_migration_0014_keeps_ai_settings_without_fallback(
    engine: AsyncEngine, db: AsyncSession
) -> None:
    """Réglage d'IA existant : le repli sur les autres IA reste désactivé (choix du parent)."""
    await db.commit()
    await run_alembic("downgrade", "0013")
    async with engine.begin() as conn:
        family_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO families (id, created_at) VALUES (:id, now())"), {"id": family_id}
        )
        await conn.execute(
            text(
                "INSERT INTO family_ai_settings (family_id, provider, updated_at) "
                "VALUES (:id, 'ollama', now())"
            ),
            {"id": family_id},
        )
    await run_alembic("upgrade", "head")
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT provider, fallback FROM family_ai_settings"))).all()
    assert [tuple(row) for row in rows] == [("ollama", False)]


async def test_migration_0015_accepts_source_searches(engine: AsyncEngine, db: AsyncSession) -> None:
    """Étape 24 : les appels « recherche de sources » sont journalisés ; retour arrière propre."""
    await db.commit()
    insert = text(
        "INSERT INTO ai_runs (id, stage, provider, model, prompt_version, latency_ms, status, warnings, "
        "created_at) VALUES (:id, 'sources', 'fake', 'fake', 'v1', 10, 'ok', '[]', now())"
    )
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4()})
    await run_alembic("downgrade", "0014")
    async with engine.connect() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM ai_runs WHERE stage = 'sources'"))).scalar()
    assert left == 0
    await run_alembic("upgrade", "head")


async def test_migration_0016_keeps_families_without_web_sources(
    engine: AsyncEngine, db: AsyncSession
) -> None:
    """Familles existantes : pas de recherche sur Internet sans l'accord du parent."""
    await db.commit()
    await run_alembic("downgrade", "0015")
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, created_at) VALUES (:id, now())"), {"id": uuid.uuid4()}
        )
    await run_alembic("upgrade", "head")
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT web_sources FROM families"))).all()
    assert [tuple(r) for r in rows] == [(False,)]


async def test_migration_0018_images_and_illustration_runs(engine: AsyncEngine, db: AsyncSession) -> None:
    """Étape 27 : une image par leçon (statut contrôlé) ; « illustration » journalisée ; retour
    arrière propre (les appels « illustration » sont effacés avec la table)."""
    ids = await create_full_lesson(db)
    await db.commit()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO lesson_images (id, lesson_id, status) VALUES (:id, :lesson, 'to_review')"),
            {"id": uuid.uuid4(), "lesson": ids["lesson"]},
        )
        await conn.execute(
            text(
                "INSERT INTO ai_runs (id, stage, provider, model, prompt_version, latency_ms, "
                "status, warnings, created_at) "
                "VALUES (:id, 'illustration', 'fake', 'fake', 'v1', 1, 'ok', '[]', now())"
            ),
            {"id": uuid.uuid4()},
        )
    with pytest.raises(IntegrityError):  # une seule image par leçon, statut connu
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO lesson_images (id, lesson_id, status) VALUES (:id, :lesson, 'bizarre')"),
                {"id": uuid.uuid4(), "lesson": ids["lesson"]},
            )
    await run_alembic("downgrade", "0017")
    async with engine.connect() as conn:
        left = (
            await conn.execute(text("SELECT count(*) FROM ai_runs WHERE stage = 'illustration'"))
        ).scalar()
    assert left == 0
    await run_alembic("upgrade", "head")


async def test_migration_0019_pictures_of_notions(engine: AsyncEngine, db: AsyncSession) -> None:
    """Étape 28 : une image pour la leçon et une par notion (pas deux) ; statut « pas utile » ;
    supprimer la notion supprime son image ; retour arrière : seule l'image de la leçon reste."""
    ids = await create_full_lesson(db)
    await db.commit()
    insert = text(
        "INSERT INTO lesson_images (id, lesson_id, knowledge_id, status) VALUES (:id, :lesson, :k, :s)"
    )
    async with engine.begin() as conn:
        await conn.execute(
            insert, {"id": uuid.uuid4(), "lesson": ids["lesson"], "k": None, "s": "not_needed"}
        )
        await conn.execute(
            insert, {"id": uuid.uuid4(), "lesson": ids["lesson"], "k": ids["knowledge"], "s": "to_review"}
        )
    for knowledge in (None, ids["knowledge"]):  # deuxième image de la leçon ou de la notion : refusée
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    insert, {"id": uuid.uuid4(), "lesson": ids["lesson"], "k": knowledge, "s": "to_review"}
                )
    await run_alembic("downgrade", "0018")
    async with engine.connect() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM lesson_images"))).scalar()
    assert left == 0  # la notion et le « pas utile » n'existaient pas avant
    await run_alembic("upgrade", "head")


async def test_migration_0020_practice_runs(engine: AsyncEngine) -> None:
    """Étape 29 : « practice » journalisée ; retour arrière propre (ces appels sont effacés)."""
    run = text(
        "INSERT INTO ai_runs (id, stage, provider, model, prompt_version, latency_ms, status, warnings, "
        "created_at) VALUES (:id, 'practice', 'fake', 'fake', 'v1', 1, 'ok', '[]', now())"
    )
    async with engine.begin() as conn:
        await conn.execute(run, {"id": uuid.uuid4()})
    await run_alembic("downgrade", "0019")
    async with engine.connect() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM ai_runs WHERE stage = 'practice'"))).scalar()
    assert left == 0
    await run_alembic("upgrade", "head")


async def test_migration_0021_lesson_resources(engine: AsyncEngine, db: AsyncSession) -> None:
    """Étape 30 : les ressources d'une leçon (site et type contrôlés, une adresse une fois) ;
    retour arrière : la table disparaît, la leçon est gardée."""
    ids = await create_full_lesson(db)
    await db.commit()
    insert = text(
        "INSERT INTO lesson_resources (id, lesson_id, provider, kind, title, url) "
        "VALUES (:id, :lesson, :provider, 'exercise', 'Fractions', :url)"
    )
    url = "https://coopmaths.fr/alea/?uuid=1"
    async with engine.begin() as conn:
        await conn.execute(
            insert, {"id": uuid.uuid4(), "lesson": ids["lesson"], "provider": "mathalea", "url": url}
        )
    for provider, address in (("mathalea", url), ("youtube", "https://youtube.com/x")):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    insert,
                    {"id": uuid.uuid4(), "lesson": ids["lesson"], "provider": provider, "url": address},
                )
    async with engine.begin() as conn:
        row = (await conn.execute(text("SELECT hidden, attempts FROM lesson_resources"))).one()
        assert tuple(row) == (False, 0)
    await run_alembic("downgrade", "0020")
    async with engine.connect() as conn:
        exists = (await conn.execute(text("SELECT to_regclass('lesson_resources')"))).scalar()
        lessons = (await conn.execute(text("SELECT count(*) FROM lessons"))).scalar()
    assert exists is None and lessons == 1
    await run_alembic("upgrade", "head")


async def test_migration_0022_help_requests(engine: AsyncEngine, db: AsyncSession) -> None:
    """Aides demandées avec leur heure : niveau 1 à 5 et type connu ; supprimer la séance les
    supprime ; retour arrière : la table disparaît, le niveau d'aide des activités reste."""
    await create_full_lesson(db)
    await db.commit()
    item = await db.scalar(select(SessionItem.id).limit(1))
    await db.commit()  # sans transaction ouverte : le retour arrière de la migration attendrait
    insert = text(
        "INSERT INTO help_requests (id, session_item_id, level, kind) VALUES (:id, :item, :level, :kind)"
    )
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "level": 1, "kind": "hint"})
    for level, kind in ((0, "hint"), (6, "answer"), (2, "devinette")):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "level": level, "kind": kind})
    async with engine.connect() as conn:
        at = (await conn.execute(text("SELECT requested_at FROM help_requests"))).scalar()
    assert at is not None  # l'heure est notée sans qu'on la donne
    await run_alembic("downgrade", "0021")
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('help_requests')"))).scalar() is None
        assert (await conn.execute(text("SELECT count(*) FROM session_items"))).scalar() == 1
    await run_alembic("upgrade", "head")
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "level": 2, "kind": "reminder"})
        await conn.execute(text("DELETE FROM session_items"))
        assert (await conn.execute(text("SELECT count(*) FROM help_requests"))).scalar() == 0


async def test_migration_0023_question_reports(engine: AsyncEngine, db: AsyncSession) -> None:
    """Questions signalées : une raison connue, une seule fois par question ; supprimer la séance
    les supprime ; retour arrière : la table disparaît, les séances restent."""
    await create_full_lesson(db)
    await db.commit()
    item = await db.scalar(select(SessionItem.id).limit(1))
    await db.commit()  # sans transaction ouverte : le retour arrière de la migration attendrait
    insert = text("INSERT INTO question_reports (id, session_item_id, reason) VALUES (:id, :item, :reason)")
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "reason": "unclear"})
    for reason in ("unclear", "c'est nul"):  # deuxième signalement, raison inconnue
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "reason": reason})
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT reported_at, seen_at FROM question_reports"))).one()
    assert row.reported_at is not None and row.seen_at is None
    await run_alembic("downgrade", "0022")
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('question_reports')"))).scalar() is None
        assert (await conn.execute(text("SELECT count(*) FROM session_items"))).scalar() == 1
    await run_alembic("upgrade", "head")
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "item": item, "reason": "right_answer"})
        await conn.execute(text("DELETE FROM session_items"))
        assert (await conn.execute(text("SELECT count(*) FROM question_reports"))).scalar() == 0


async def test_migration_0024_homework(engine: AsyncEngine, db: AsyncSession) -> None:
    """Mode devoirs : statut et origine connus ; supprimer l'enfant supprime ses devoirs ;
    `ai_runs` accepte l'étape `homework` ; retour arrière : table et étape disparaissent."""
    await create_full_lesson(db)
    await db.commit()
    child = await db.scalar(select(Child.id).limit(1))
    await db.commit()  # sans transaction ouverte : le retour arrière de la migration attendrait
    insert = text(
        "INSERT INTO homework (id, child_id, status, source) VALUES (:id, :child, :status, :source)"
    )
    async with engine.begin() as conn:
        await conn.execute(
            insert, {"id": uuid.uuid4(), "child": child, "status": "preparing", "source": "text"}
        )
        await conn.execute(
            text(
                "INSERT INTO ai_runs (id, stage, provider, model, prompt_version, latency_ms, status) "
                "VALUES (:id, 'homework', 'fake', 'fake', 'v1', 1, 'ok')"
            ),
            {"id": uuid.uuid4()},
        )
    for status, source in (("en cours", "text"), ("ready", "papier")):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    insert, {"id": uuid.uuid4(), "child": child, "status": status, "source": source}
                )
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT steps_shown, attempts FROM homework"))).one()
    assert row.steps_shown == 0 and row.attempts == []
    await run_alembic("downgrade", "0023")
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('homework')"))).scalar() is None
        assert (
            await conn.execute(text("SELECT count(*) FROM ai_runs WHERE stage = 'homework'"))
        ).scalar() == 0
    await run_alembic("upgrade", "head")
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "child": child, "status": "ready", "source": "photo"})
        await conn.execute(text("DELETE FROM children"))
        assert (await conn.execute(text("SELECT count(*) FROM homework"))).scalar() == 0


async def test_migration_0025_teach(engine: AsyncEngine, db: AsyncSession) -> None:
    """« Enseigne-moi » : statut connu ; supprimer la leçon supprime ses conversations ; `ai_runs`
    accepte l'étape `teach` ; retour arrière : table et étape disparaissent."""
    await create_full_lesson(db)
    await db.commit()
    child = await db.scalar(select(Child.id).limit(1))
    lesson, knowledge = (await db.execute(text("SELECT lesson_id, id FROM knowledge_items LIMIT 1"))).one()
    await db.commit()  # sans transaction ouverte : le retour arrière de la migration attendrait
    insert = text(
        "INSERT INTO teach_sessions (id, child_id, lesson_id, knowledge_id, status, key_points) "
        "VALUES (:id, :child, :lesson, :knowledge, :status, '[\"un point\"]')"
    )
    values = {"child": child, "lesson": lesson, "knowledge": knowledge}
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "status": "open", **values})
        await conn.execute(
            text(
                "INSERT INTO ai_runs (id, stage, provider, model, prompt_version, latency_ms, status) "
                "VALUES (:id, 'teach', 'fake', 'fake', 'v1', 1, 'ok')"
            ),
            {"id": uuid.uuid4()},
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(insert, {"id": uuid.uuid4(), "status": "en cours", **values})
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT turns, covered, validated FROM teach_sessions"))).one()
    assert row.turns == [] and row.covered is None and row.validated is None
    await run_alembic("downgrade", "0024")
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('teach_sessions')"))).scalar() is None
        assert (await conn.execute(text("SELECT count(*) FROM ai_runs WHERE stage = 'teach'"))).scalar() == 0
    await run_alembic("upgrade", "head")
    async with engine.begin() as conn:
        await conn.execute(insert, {"id": uuid.uuid4(), "status": "finished", **values})
        await conn.execute(text("DELETE FROM lessons"))
        assert (await conn.execute(text("SELECT count(*) FROM teach_sessions"))).scalar() == 0
