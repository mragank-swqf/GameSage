import os
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql+asyncpg://gamesage:gamesage@postgres:5432/gamesage",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one async DB session per request (injected via FastAPI Depends)."""
    async with async_session_factory() as session:
        yield session


async def verify_db_connection() -> None:
    """Ping Postgres on startup to confirm the pool can connect."""
    async with engine.connect() as connection:
        await connection.execute(select(1))


async def close_db() -> None:
    """Dispose the connection pool on shutdown."""
    await engine.dispose()
