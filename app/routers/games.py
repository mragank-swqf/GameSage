"""Games discovery endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Game
from app.db.session import get_db
from app.schemas.game_schemas import (
    CocPlayerResponse,
    GameResponse,
    GameTopicsResponse,
)
from app.services import coc_api, qdrant as qdrant_service
from app.services.coc_api import CocApiError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Games"])


@router.get(
    "/games",
    response_model=list[GameResponse],
    description="List all supported games (genre, modes, live-api flag).",
    response_description="All rows from the games table.",
)
async def list_games(db: AsyncSession = Depends(get_db)) -> list[Game]:
    result = await db.execute(select(Game).order_by(Game.id))
    games = list(result.scalars().all())
    logger.info("Listed %d games", len(games))
    return games


@router.get(
    "/games/coc/player/{player_tag}",
    response_model=CocPlayerResponse,
    description=(
        "Fetch live Clash of Clans player data by tag "
        "(town hall, trophies, war stars, heroes). "
        "Pass tag without #, e.g. ABC123XYZ — or URL-encoded %23ABC123XYZ."
    ),
    response_description="Mapped CoC player snapshot from the official API.",
)
async def get_coc_player(player_tag: str) -> CocPlayerResponse:
    try:
        data = await coc_api.get_player(player_tag)
    except CocApiError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from None

    return CocPlayerResponse.model_validate(data)


@router.get(
    "/games/{game_id}/topics",
    response_model=GameTopicsResponse,
    description=(
        "List distinct weakness_category values covered in Qdrant for this game "
        "(what RAG can actually retrieve)."
    ),
    response_description="Game identity plus sorted topic/weakness labels from the corpus.",
)
async def get_game_topics(
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> GameTopicsResponse:
    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {game_id} not found",
        )

    try:
        topics = qdrant_service.list_weakness_categories_for_game(game.name)
    except Exception:
        logger.exception("Qdrant topics lookup failed for game=%s", game.name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach Qdrant to list topics",
        ) from None

    return GameTopicsResponse(
        game_id=game.id,
        game=game.name,
        display_name=game.display_name,
        topics=topics,
    )
