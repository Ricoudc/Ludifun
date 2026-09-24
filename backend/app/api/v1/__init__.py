from fastapi import APIRouter

from app.api.v1 import ai_settings, auth, children, dashboard, feedback, goals, lessons, rewards, sessions

router = APIRouter(prefix="/v1")
router.include_router(ai_settings.router)
router.include_router(auth.router)
router.include_router(children.router)
router.include_router(dashboard.router)
router.include_router(feedback.router)
router.include_router(goals.router)
router.include_router(lessons.router)
router.include_router(rewards.router)
router.include_router(sessions.router)
