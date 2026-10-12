from fastapi import APIRouter

from app.api.v1 import (
    ai_settings,
    auth,
    children,
    dashboard,
    feedback,
    figures,
    goals,
    homework,
    lesson_content,
    lesson_images,
    lesson_resources,
    lessons,
    notebook,
    phone_app,
    rewards,
    sessions,
    teach,
)

router = APIRouter(prefix="/v1")
router.include_router(ai_settings.router)
router.include_router(auth.router)
router.include_router(children.router)
router.include_router(dashboard.router)
router.include_router(feedback.router)
router.include_router(figures.router)
router.include_router(goals.router)
router.include_router(homework.router)
router.include_router(lesson_content.router)
router.include_router(lesson_images.router)
router.include_router(lesson_resources.router)
router.include_router(lessons.router)
router.include_router(notebook.router)
router.include_router(phone_app.router)
router.include_router(rewards.router)
router.include_router(sessions.router)
router.include_router(teach.router)
