import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.db.session import async_session_factory, close_db, verify_db_connection
from app.routers import games, players, users
from app.schemas.health_schemas import HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open DB pool on startup, close it on shutdown."""
    logger.info("Starting up — opening database connection pool")
    await verify_db_connection()
    logger.info("Database connection pool ready")
    yield
    logger.info("Shutting down — closing database connection pool")
    await close_db()


app = FastAPI(
    title="GameSage",
    description=(
        "Stateful AI game mastery agent — personalized strategy, loadout, and "
        "gameplay suggestions grounded in your stats, goals, and past sessions."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(games.router)
app.include_router(players.router)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    description="Check that the API is running and can reach Postgres.",
    response_description="Service status and database connectivity.",
)
async def health_check() -> HealthResponse:
    postgres_status = "connected"
    try:
        async with async_session_factory() as session:
            await session.execute(select(1))
    except Exception:
        logger.exception("Health check failed — cannot reach Postgres")
        postgres_status = "unavailable"

    overall_status = "ok" if postgres_status == "connected" else "degraded"
    return HealthResponse(status=overall_status, postgres=postgres_status)
