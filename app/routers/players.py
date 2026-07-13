"""Player stats submit + retrieve endpoints."""

import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Game, PlayerStat, User
from app.db.session import get_db
from app.schemas.player_schemas import PlayerStatsCreate, PlayerStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Players"])


async def _latest_stats(
    db: AsyncSession,
    user_id: int,
    game_id: int,
) -> PlayerStat | None:
    result = await db.execute(
        select(PlayerStat)
        .where(PlayerStat.user_id == user_id, PlayerStat.game_id == game_id)
        .order_by(PlayerStat.submitted_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post(
    "/players/{user_id}/stats",
    response_model=PlayerStatsResponse,
    description=(
        "Submit or update player stats for a game "
        "(rank, KD, weapons, goals, known weaknesses). "
        "Upserts the latest row for this user+game."
    ),
    response_description="The stored player_stats row.",
)
async def upsert_player_stats(
    user_id: int,
    body: PlayerStatsCreate,
    db: AsyncSession = Depends(get_db),
) -> PlayerStat:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    game = await db.get(Game, body.game_id)
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {body.game_id} not found",
        )

    stats = await _latest_stats(db, user_id, body.game_id)
    fields = {
        "current_rank": body.current_rank,
        "kd_ratio": body.kd_ratio,
        "win_rate": body.win_rate,
        "weekly_playtime_hours": body.weekly_playtime_hours,
        "preferred_weapons": body.preferred_weapons,
        "known_weaknesses": body.known_weaknesses,
        "goals": body.goals,
        "source": "user_submitted",
    }

    if stats is None:
        stats = PlayerStat(user_id=user_id, game_id=body.game_id, **fields)
        db.add(stats)
        logger.info(
            "Created player_stats user_id=%s game_id=%s", user_id, body.game_id
        )
    else:
        for key, value in fields.items():
            setattr(stats, key, value)
        stats.submitted_at = datetime.now(timezone.utc)
        logger.info(
            "Updated player_stats user_id=%s game_id=%s id=%s",
            user_id,
            body.game_id,
            stats.id,
        )

    await db.commit()
    await db.refresh(stats)
    return stats


@router.get(
    "/players/{user_id}/stats/{game_id}",
    response_model=PlayerStatsResponse,
    description="Fetch the latest submitted stats for a user and game.",
    response_description="Latest player_stats row for this user+game.",
)
async def get_player_stats(
    user_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> PlayerStat:
    stats = await _latest_stats(db, user_id, game_id)
    if stats is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stats for user {user_id} and game {game_id}",
        )
    return stats
