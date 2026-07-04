"""Seed the games table with all 6 supported titles."""

import asyncio
import logging
from typing import TypedDict

from sqlalchemy import select

from app.db.models import Game
from app.db.session import async_session_factory, close_db

logger = logging.getLogger(__name__)


class GameSeed(TypedDict):
    name: str
    display_name: str
    genre: str
    supported_modes: list[str]
    has_live_api: bool


GAMES: list[GameSeed] = [
    {
        "name": "gta_v_online",
        "display_name": "GTA V Online",
        "genre": "open_world",
        "supported_modes": ["online", "missions", "freeroam"],
        "has_live_api": False,
    },
    {
        "name": "rdr2",
        "display_name": "Red Dead Redemption 2",
        "genre": "open_world",
        "supported_modes": ["story", "online"],
        "has_live_api": False,
    },
    {
        "name": "cod",
        "display_name": "Call of Duty",
        "genre": "shooter",
        "supported_modes": ["warzone", "multiplayer", "ranked"],
        "has_live_api": False,
    },
    {
        "name": "coc",
        "display_name": "Clash of Clans",
        "genre": "strategy",
        "supported_modes": ["multiplayer", "clan_wars"],
        "has_live_api": True,
    },
    {
        "name": "cr",
        "display_name": "Clash Royale",
        "genre": "strategy",
        "supported_modes": ["ranked", "ladder"],
        "has_live_api": True,
    },
    {
        "name": "free_fire",
        "display_name": "Garena Free Fire",
        "genre": "shooter",
        "supported_modes": ["battle_royale", "ranked", "classic"],
        "has_live_api": False,
    },
]


async def seed_games() -> None:
    """Insert games that are not already in the database."""
    inserted = 0
    skipped = 0

    async with async_session_factory() as session:
        for game_data in GAMES:
            existing = await session.scalar(
                select(Game).where(Game.name == game_data["name"])
            )
            if existing:
                logger.info("Skipping %s — already exists", game_data["name"])
                skipped += 1
                continue

            session.add(Game(**game_data))
            logger.info("Inserted %s", game_data["display_name"])
            inserted += 1

        await session.commit()

    logger.info("Seed complete — inserted: %d, skipped: %d", inserted, skipped)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed_games()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
