from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routers import children, lessons, sessions


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Ludifun API",
    description="Coach de révision : photo d'une leçon → notions → jeux → révisions adaptées.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(children.router)
app.include_router(lessons.router)
app.include_router(sessions.router)


@app.get("/health", tags=["système"])
def health() -> dict[str, str]:
    return {"status": "ok"}
