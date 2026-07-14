"""Step 1 — assemble a unified player context for the mastery pipeline."""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Game, PlayerStat, UserProfile
from app.services import coc_api, cr_api
from app.services.coc_api import CocApiError
from app.services.cr_api import CrApiError

logger = logging.getLogger(__name__)

# Supercell player tags use a limited alphabet (no 1, I, O, etc.)
_TAG_IN_NOTES = re.compile(r"#?([0289PYLQGRJCUV][0289PYLQGRJCUV0-9]{2,})", re.IGNORECASE)


class AssemblerError(Exception):
    """Raised when context cannot be assembled (missing stats, unknown game, …)."""

    def __init__(self, message: str, *, step: str = "assembler") -> None:
        super().__init__(message)
        self.step = step


def _json_safe(value: Any) -> Any:
    """Convert Decimal / nested values into JSON-friendly Python types."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def extract_player_tag(notes: str | None, explicit: str | None = None) -> str | None:
    """Resolve a CoC/CR tag from an explicit arg or profile notes."""
    if explicit and explicit.strip():
        return explicit.strip()
    if not notes:
        return None
    match = _TAG_IN_NOTES.search(notes)
    return match.group(0) if match else None


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


async def _fetch_live(
    game_name: str,
    player_tag: str,
) -> dict[str, Any] | None:
    """Call CoC or CR live API. Returns None on soft failure (logged)."""
    try:
        if game_name == "coc":
            return await coc_api.get_player(player_tag)
        if game_name == "cr":
            return await cr_api.get_player(player_tag)
    except (CocApiError, CrApiError) as exc:
        logger.warning(
            "Live API merge skipped for game=%s tag=%s: %s",
            game_name,
            player_tag,
            exc,
        )
        return None
    except Exception:
        logger.exception(
            "Unexpected live API error for game=%s tag=%s", game_name, player_tag
        )
        return None
    logger.warning("Game %s has_live_api but no client wired", game_name)
    return None


async def assemble_context(
    user_id: int,
    game_id: int,
    db: AsyncSession,
    *,
    player_tag: str | None = None,
) -> dict[str, Any]:
    """
    Build the unified player context dict used by every later agent step.

    Takes: user_id, game_id, async DB session, optional live player_tag.
    Returns: dict with game, profile, stats, live (optional), source.
    Calls: Postgres (always); CoC/CR HTTP clients when has_live_api and a tag exist.

    Raises AssemblerError if the game is missing or no player_stats row exists.
    """
    game = await db.get(Game, game_id)
    if game is None:
        raise AssemblerError(f"Game {game_id} not found")

    profile_result = await db.execute(
        select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.game_id == game_id,
        )
    )
    profile = profile_result.scalar_one_or_none()

    stats = await _latest_stats(db, user_id, game_id)
    if stats is None:
        raise AssemblerError(
            f"Submit player stats via POST /players/{user_id}/stats before assessment"
        )

    profile_payload = None
    if profile is not None:
        profile_payload = {
            "experience_level": profile.experience_level,
            "preferred_playstyle": profile.preferred_playstyle,
            "notes": profile.notes,
        }

    stats_payload = {
        "current_rank": stats.current_rank,
        "kd_ratio": _json_safe(stats.kd_ratio),
        "win_rate": _json_safe(stats.win_rate),
        "weekly_playtime_hours": _json_safe(stats.weekly_playtime_hours),
        "preferred_weapons": stats.preferred_weapons,
        "known_weaknesses": stats.known_weaknesses,
        "goals": stats.goals,
        "source": stats.source,
        "submitted_at": stats.submitted_at.isoformat() if stats.submitted_at else None,
    }

    live_payload: dict[str, Any] | None = None
    source = "user_submitted"

    if game.has_live_api:
        notes = profile.notes if profile else None
        tag = extract_player_tag(notes, player_tag)
        if tag:
            live_payload = await _fetch_live(game.name, tag)
            if live_payload is not None:
                source = "merged"
        else:
            logger.info(
                "Game %s has live API but no player tag "
                "(pass player_tag= or put #TAG in profile notes)",
                game.name,
            )

    context = {
        "user_id": user_id,
        "game_id": game_id,
        "game": {
            "name": game.name,
            "display_name": game.display_name,
            "genre": game.genre,
            "has_live_api": game.has_live_api,
        },
        "profile": profile_payload,
        "stats": stats_payload,
        "live": live_payload,
        "source": source,
    }
    logger.info(
        "Assembled context user_id=%s game=%s source=%s live=%s",
        user_id,
        game.name,
        source,
        live_payload is not None,
    )
    return context
