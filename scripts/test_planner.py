"""Manual test for Step 4 generate_plan (mock assess + real retrieve + Gemini).

Does not call the assessor LLM (saves quota). Uses a CoC mock assessment.

  docker compose exec api python scripts/test_planner.py --user-id 1 --game-id 4
  docker compose exec api python scripts/test_planner.py --user-id 1 --game-id 4 --store
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
from app.agent.assessor import AssessmentResult
from app.agent.planner import PlannerError, generate_plan
from app.agent.retriever import retrieve
from app.db.models import CoachingPlan

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
    if not os.path.exists("/.dockerenv") and os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"

    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--game-id", type=int, required=True)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow CoC/CR live merge (default: skip)",
    )
    parser.add_argument(
        "--store",
        action="store_true",
        help="Persist plan to coaching_plans (Feature 3)",
    )
    args = parser.parse_args()

    # Mock assessment — taxonomy-valid for strategy games (coc/cr)
    assessment = AssessmentResult(
        weaknesses=["troop_deployment", "base_layout"],
        skill_tier="intermediate",
        priority_focus="troop_deployment",
    )

    engine = create_async_engine(resolve_db_url(), echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with factory() as db:
            context = await assemble_context(
                args.user_id,
                args.game_id,
                db,
                skip_live=not args.live,
            )
            chunks = retrieve(assessment, context)
            plan = await generate_plan(
                context,
                assessment,
                chunks,
                db,
                persist=args.store,
            )

            if args.store and plan.plan_id is not None:
                row = await db.get(CoachingPlan, plan.plan_id)
                logger.info(
                    "DB row id=%s weaknesses=%s chunk_ids=%s expires=%s",
                    row.id if row else None,
                    row.identified_weaknesses if row else None,
                    row.retrieved_chunk_ids if row else None,
                    row.expires_at.isoformat() if row and row.expires_at else None,
                )

        out = plan.to_dict()
        out.pop("raw_model_text", None)
        print(json.dumps(out, indent=2, default=str))
        logger.info(
            "OK — days=%d loadouts=%d chunk_ids=%d plan_id=%s",
            len(plan.seven_day_plan),
            len(plan.loadout_recommendations),
            len(plan.retrieved_chunk_ids),
            plan.plan_id,
        )
    except (AssemblerError, PlannerError) as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
