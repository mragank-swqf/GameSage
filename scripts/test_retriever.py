"""Manual test for Day 6 Feature 1 — weakness-conditioned retrieval (mock assessment).

Does NOT call the assessor LLM — uses a fixed AssessmentResult so we can ship
retrieval while Gemini generation is flaky. Keep test_assessor.py for later.

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
from app.agent.retriever import retrieve

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock assessments per game (taxonomy-valid weaknesses)
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
        weaknesses=["positioning", "loadout"],
        skill_tier="intermediate",
        priority_focus="positioning",
    ),
    "free_fire": AssessmentResult(
        weaknesses=["aim", "movement"],
        skill_tier="intermediate",
        priority_focus="aim",
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


def main() -> None:
    load_dotenv()
    # Host → published Qdrant; container → service name
    if not os.path.exists("/.dockerenv") and os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"

    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True, choices=sorted(MOCKS.keys()))
    parser.add_argument("--experience-level", default="intermediate")
    args = parser.parse_args()

    assessment = MOCKS[args.game]
    context = {
        "game": {"name": args.game, "genre": "n/a", "has_live_api": False},
        "profile": {"experience_level": args.experience_level},
        "stats": {},
        "live": None,
        "source": "user_submitted",
    }

    chunks = retrieve(assessment, context)
    # Compact print for terminal
    printable = [
        {
            "chunk_id": c.chunk_id,
            "score": round(c.score, 4),
            "weakness_queried": c.weakness_queried,
            "weakness_category": c.weakness_category,
            "skill_level": c.skill_level,
            "heading": c.heading,
            "preview": (c.content or "")[:120],
        }
        for c in chunks
    ]
    print(json.dumps({"game": args.game, "count": len(chunks), "chunks": printable}, indent=2))

    bad_game = [c for c in chunks if c.game and c.game != args.game]
    bad_weak = [
        c
        for c in chunks
        if c.weakness_category and c.weakness_category != c.weakness_queried
    ]
    if bad_game:
        logger.error("WRONG GAME in %d hits", len(bad_game))
        sys.exit(1)
    if bad_weak:
        logger.error("WEAKNESS MISMATCH in %d hits", len(bad_weak))
        sys.exit(1)

    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        logger.error("DUPLICATE chunk_ids after merge")
        sys.exit(1)
    if len(chunks) > 15:
        logger.error("Cap broken: got %d chunks (max 15)", len(chunks))
        sys.exit(1)
    if len(chunks) >= 2:
        scores = [c.score for c in chunks]
        if scores != sorted(scores, reverse=True):
            logger.error("Chunks not sorted by score descending")
            sys.exit(1)

    if not chunks:
        logger.warning("0 chunks — filters may be too tight for this corpus tier")
    else:
        logger.info(
            "OK — %d unique chunks, sorted, capped, game+weakness filters sane",
            len(chunks),
        )


if __name__ == "__main__":
    main()
