from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database


def get_database(request: Request) -> Database:
    db: Database = request.app.state.database
    return db


async def get_db(database: Annotated[Database, Depends(get_database)]) -> AsyncIterator[AsyncSession]:
    async for session in database.session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
