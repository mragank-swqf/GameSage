"""Manual sanity check for Step 2 assess(context).

  docker compose exec api python scripts/test_assessor.py --user-id 1 --game-id 4 --player-tag P28jpgrlj
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
from app.agent.assessor import AssessorError, assess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resolve_db_url() -> str:
    db_url = os.getenv(
        "POSTGRES_URL",
        "postgresql+asyncpg://gamesage:gamesage@localhost:5432/gamesage",
    )
    if os.path.exists("/.dockerenv"):
        return db_url
    if "@postgres:" in db_url:
        return db_url.replace("@postgres:", "@localhost:")
    return db_url


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--game-id", type=int, required=True)
    parser.add_argument("--player-tag", type=str, default=None)
    args = parser.parse_args()

    engine = create_async_engine(resolve_db_url(), echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with factory() as db:
            context = await assemble_context(
                args.user_id, args.game_id, db, player_tag=args.player_tag
            )
            result = await assess(context, db)
        print(json.dumps(result.to_dict(), indent=2))
    except (AssemblerError, AssessorError) as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
