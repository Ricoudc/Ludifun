from fastapi import APIRouter

from app.api.v1 import auth, children, dashboard, lessons, sessions

router = APIRouter(prefix="/v1")
router.include_router(auth.router)
router.include_router(children.router)
router.include_router(dashboard.router)
router.include_router(lessons.router)
router.include_router(sessions.router)
