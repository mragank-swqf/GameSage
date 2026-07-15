import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.agent.errors import AgentPipelineHTTPError
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


@app.exception_handler(AgentPipelineHTTPError)
async def agent_pipeline_error_handler(
    _request: Request,
    exc: AgentPipelineHTTPError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "step": exc.step,
            "fallback_used": exc.fallback_used,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "step": "unknown",
            "fallback_used": False,
        },
    )


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
