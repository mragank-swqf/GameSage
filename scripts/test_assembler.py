"""Manual sanity check for Step 1 assemble_context.

Usage (Postgres reachable on localhost:5432):

  python scripts/test_assembler.py --user-id 1 --game-id 4 --player-tag P28jpgrlj

Expects user + player_stats (and ideally profile) to already exist.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.assembler import AssemblerError, assemble_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Test assemble_context")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--game-id", type=int, required=True)
    parser.add_argument("--player-tag", type=str, default=None)
    args = parser.parse_args()

    db_url = os.getenv(
        "POSTGRES_URL",
        "postgresql+asyncpg://gamesage:gamesage@localhost:5432/gamesage",
    )
    if "@postgres:" in db_url:
        db_url = db_url.replace("@postgres:", "@localhost:")

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with factory() as db:
            context = await assemble_context(
                args.user_id,
                args.game_id,
                db,
                player_tag=args.player_tag,
            )
        print(json.dumps(context, indent=2))
    except AssemblerError as exc:
        logger.error("AssemblerError: %s", exc)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
