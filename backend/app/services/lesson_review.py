"""Relecture par le parent (§5.69) : l'IA peut se tromper ; quand la famille relit ses leçons
(« Je relis chaque leçon avant mon enfant », coché par défaut), une leçon prête attend que le
parent la valide avant d'être ouverte ou jouée par l'enfant.

Le réglage est lu au moment de l'accès : décocher la case ouvre aussitôt les leçons en attente.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db

AWAITING_MESSAGE = "Un adulte relit ta leçon avant que tu la révises. Elle arrive bientôt !"


async def family_reviews(session: AsyncSession, family_id: object) -> bool:
    return bool(await session.scalar(select(db.Family.review_lessons).where(db.Family.id == family_id)))


async def awaiting_parent(session: AsyncSession, lesson: db.Lesson) -> bool:
    """La leçon est prête mais le parent ne l'a pas encore validée, et la famille relit."""
    if lesson.status != "ready" or lesson.parent_approved_at is not None:
        return False
    family = await session.scalar(select(db.Child.family_id).where(db.Child.id == lesson.child_id))
    return await family_reviews(session, family)
