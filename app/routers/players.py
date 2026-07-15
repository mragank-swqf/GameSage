"""Player stats + assess (full 4-step mastery pipeline) endpoints."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.assembler import AssemblerError, assemble_context
from app.agent.assessor import AssessorError, assess
from app.agent.errors import AgentPipelineHTTPError
from app.agent.planner import PlannerError, generate_plan
from app.agent.retriever import retrieve
from app.db.models import CoachingPlan, Game, PlayerStat, User
from app.db.session import get_db
from app.schemas.player_schemas import (
    AssessRequest,
    AssessResponse,
    AssessmentSummary,
    PlayerStatsCreate,
    PlayerStatsResponse,
)

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


@router.post(
    "/players/{user_id}/assess/{game_id}",
    response_model=AssessResponse,
    description=(
        "Run the full mastery pipeline: assemble context → assess weaknesses → "
        "retrieve strategy chunks → generate and store a 7-day plan."
    ),
    response_description="Stored mastery plan plus assessment summary.",
)
async def assess_player(
    user_id: int,
    game_id: int,
    body: AssessRequest = Body(default_factory=AssessRequest),
    db: AsyncSession = Depends(get_db),
) -> AssessResponse:
    """
    Wire Steps 1–4 for one user+game.

    Takes: path user_id/game_id, optional AssessRequest (player_tag, skip_live).
    Returns: AssessResponse with plan_id and full plan payload.
    Calls: assemble_context, assess, retrieve, generate_plan(persist=True).
    """
    user = await db.get(User, user_id)
    if user is None:
        raise AgentPipelineHTTPError(
            f"User {user_id} not found",
            step="assembler",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    game = await db.get(Game, game_id)
    if game is None:
        raise AgentPipelineHTTPError(
            f"Game {game_id} not found",
            step="assembler",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    started = time.perf_counter()
    try:
        t0 = time.perf_counter()
        context = await assemble_context(
            user_id,
            game_id,
            db,
            player_tag=body.player_tag,
            skip_live=body.skip_live,
        )
        logger.info(
            "Pipeline step=assembler ok (%.0fms)",
            (time.perf_counter() - t0) * 1000,
        )

        t0 = time.perf_counter()
        assessment = await assess(context, db)
        logger.info(
            "Pipeline step=assessor ok (%.0fms)",
            (time.perf_counter() - t0) * 1000,
        )

        t0 = time.perf_counter()
        chunks = retrieve(assessment, context)
        logger.info(
            "Pipeline step=retriever ok chunks=%d (%.0fms)",
            len(chunks),
            (time.perf_counter() - t0) * 1000,
        )

        t0 = time.perf_counter()
        plan = await generate_plan(
            context,
            assessment,
            chunks,
            db,
            persist=True,
        )
        logger.info(
            "Pipeline step=planner ok (%.0fms)",
            (time.perf_counter() - t0) * 1000,
        )
    except AssemblerError as exc:
        code = status.HTTP_400_BAD_REQUEST
        if "not found" in str(exc).lower():
            code = status.HTTP_404_NOT_FOUND
        raise AgentPipelineHTTPError(
            str(exc),
            step=getattr(exc, "step", "assembler"),
            status_code=code,
        ) from exc
    except AssessorError as exc:
        raise AgentPipelineHTTPError(
            str(exc),
            step=getattr(exc, "step", "assessor"),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except PlannerError as exc:
        raise AgentPipelineHTTPError(
            str(exc),
            step=getattr(exc, "step", "planner"),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except ValueError as exc:
        raise AgentPipelineHTTPError(
            str(exc),
            step="retriever",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    if plan.plan_id is None:
        raise AgentPipelineHTTPError(
            "Plan generated but not persisted",
            step="planner",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    row = await db.get(CoachingPlan, plan.plan_id)
    retrieval_empty = len(plan.retrieved_chunk_ids) == 0
    fallback_used = bool(assessment.fallback_used) or retrieval_empty

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Pipeline done user=%s game=%s plan_id=%s chunks=%d fallback=%s (%.0fms)",
        user_id,
        game_id,
        plan.plan_id,
        len(plan.retrieved_chunk_ids),
        fallback_used,
        elapsed_ms,
    )

    return AssessResponse(
        plan_id=plan.plan_id,
        user_id=user_id,
        game_id=game_id,
        assessment=AssessmentSummary(
            weaknesses=assessment.weaknesses,
            skill_tier=assessment.skill_tier,
            priority_focus=assessment.priority_focus,
            fallback_used=assessment.fallback_used,
        ),
        skill_assessment=plan.skill_assessment,
        seven_day_plan=plan.seven_day_plan,
        loadout_recommendations=plan.loadout_recommendations,
        rank_roadmap=plan.rank_roadmap,
        experience_level=plan.experience_level,
        retrieved_chunk_ids=plan.retrieved_chunk_ids,
        chunk_count=len(plan.retrieved_chunk_ids),
        fallback_used=fallback_used,
        generated_at=row.generated_at if row else None,
        expires_at=row.expires_at if row else None,
    )
