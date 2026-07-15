"""Day 6 Feature 4 — retrieval quality check across all 6 games.

Uses mock assessments (no assessor LLM). Verifies:
  - chunks are from the requested game
  - weakness_category matches the weakness we queried
  - skill_level matches assessment.skill_tier when present
  - merge rules: unique ids, sorted by score, <= 15
  - at least 1 chunk (else corpus/filter gap)

Usage:
  docker compose exec api python scripts/test_retriever.py --all
  docker compose exec api python scripts/test_retriever.py --game coc
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.assessor import AssessmentResult
from app.agent.retriever import chunk_ids_for_audit, retrieve

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mocks prefer weakness labels that exist in the ingested corpus.
# CoD has almost no `positioning` chunks → game_sense + loadout.
MOCKS: dict[str, AssessmentResult] = {
    "coc": AssessmentResult(
        weaknesses=["troop_deployment", "base_layout"],
        skill_tier="intermediate",
        priority_focus="troop_deployment",
    ),
    "cr": AssessmentResult(
        weaknesses=["deck_building", "timing"],
        skill_tier="intermediate",
        priority_focus="deck_building",
    ),
    "cod": AssessmentResult(
        weaknesses=["game_sense", "loadout"],
        skill_tier="intermediate",
        priority_focus="loadout",
    ),
    "free_fire": AssessmentResult(
        weaknesses=["aim", "loadout"],
        skill_tier="intermediate",
        priority_focus="loadout",
    ),
    "gta_v_online": AssessmentResult(
        weaknesses=["mission_strategy", "money_making"],
        skill_tier="intermediate",
        priority_focus="mission_strategy",
    ),
    "rdr2": AssessmentResult(
        weaknesses=["combat", "stealth"],
        skill_tier="intermediate",
        priority_focus="combat",
    ),
}


def _configure_host_qdrant() -> None:
    if not os.path.exists("/.dockerenv") and os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"


def run_one(game: str, experience_level: str) -> dict:
    """Run retrieval for one game; raise AssertionError on quality failures."""
    assessment = MOCKS[game]
    context = {
        "game": {"name": game, "genre": "n/a", "has_live_api": False},
        "profile": {"experience_level": experience_level},
        "stats": {},
        "live": None,
        "source": "user_submitted",
    }
    chunks = retrieve(assessment, context)

    bad_game = [c for c in chunks if c.game and c.game != game]
    if bad_game:
        raise AssertionError(f"{game}: {len(bad_game)} hits from wrong game")

    bad_weak = [
        c
        for c in chunks
        if c.weakness_category and c.weakness_category != c.weakness_queried
    ]
    if bad_weak:
        raise AssertionError(f"{game}: {len(bad_weak)} weakness mismatches")

    bad_skill = [
        c
        for c in chunks
        if c.skill_level and c.skill_level != assessment.skill_tier
    ]
    if bad_skill:
        raise AssertionError(
            f"{game}: {len(bad_skill)} skill_level mismatches "
            f"(wanted {assessment.skill_tier})"
        )

    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"{game}: duplicate chunk_ids after merge")
    if len(chunks) > 15:
        raise AssertionError(f"{game}: cap broken ({len(chunks)} > 15)")
    if len(chunks) >= 2:
        scores = [c.score for c in chunks]
        if scores != sorted(scores, reverse=True):
            raise AssertionError(f"{game}: not sorted by score desc")

    if not chunks:
        raise AssertionError(
            f"{game}: 0 chunks — corpus gap or filters too tight for "
            f"{assessment.weaknesses} / {assessment.skill_tier}"
        )

    return {
        "game": game,
        "count": len(chunks),
        "weaknesses": assessment.weaknesses,
        "skill_tier": assessment.skill_tier,
        "audit_trail_chunk_ids": chunk_ids_for_audit(chunks),
        "sample": [
            {
                "chunk_id": c.chunk_id,
                "score": round(c.score, 4),
                "weakness_queried": c.weakness_queried,
                "weakness_category": c.weakness_category,
                "skill_level": c.skill_level,
                "heading": c.heading,
            }
            for c in chunks[:3]
        ],
    }


def main() -> None:
    load_dotenv()
    _configure_host_qdrant()

    parser = argparse.ArgumentParser(description="Retrieval quality test")
    parser.add_argument(
        "--game",
        choices=sorted(MOCKS.keys()),
        help="Single game (omit if using --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run quality checks for all 6 games",
    )
    parser.add_argument("--experience-level", default="intermediate")
    args = parser.parse_args()

    if args.all:
        games = list(MOCKS.keys())
    elif args.game:
        games = [args.game]
    else:
        parser.error("Pass --game NAME or --all")

    summary: list[dict] = []
    failures: list[str] = []

    for game in games:
        try:
            row = run_one(game, args.experience_level)
            summary.append(row)
            logger.info("PASS %s — %d chunks", game, row["count"])
        except Exception as exc:
            failures.append(f"{game}: {exc}")
            logger.error("FAIL %s — %s", game, exc)

    print(json.dumps({"results": summary, "failures": failures}, indent=2))

    if failures:
        logger.error("%d / %d games failed", len(failures), len(games))
        sys.exit(1)

    logger.info("ALL PASS — %d games", len(games))


if __name__ == "__main__":
    main()
