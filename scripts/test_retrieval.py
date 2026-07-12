"""Manual retrieval sanity checks against Qdrant (Day 3 Feature 6)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.gemini import embed_text  # noqa: E402
from app.services.qdrant import collection_info, get_qdrant_client, search  # noqa: E402

logger = logging.getLogger(__name__)


def _host_override() -> None:
    if os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"


def run_query(
    label: str,
    query: str,
    *,
    game: str,
    weakness_category: str | None = None,
    skill_level: str | None = None,
    limit: int = 5,
) -> list[dict]:
    logger.info("=" * 60)
    logger.info("TEST: %s", label)
    logger.info(
        "query=%r game=%s weakness=%s skill=%s",
        query,
        game,
        weakness_category,
        skill_level,
    )
    vector = embed_text(query, task_type="RETRIEVAL_QUERY")
    hits = search(
        vector,
        game=game,
        weakness_category=weakness_category,
        skill_level=skill_level,
        limit=limit,
    )
    if not hits:
        logger.warning("No hits returned")
        return hits

    for i, hit in enumerate(hits, start=1):
        logger.info(
            "  #%d score=%.4f game=%s weakness=%s skill=%s chunk=%s",
            i,
            hit["score"],
            hit["game"],
            hit["weakness_category"],
            hit["skill_level"],
            hit["chunk_id"],
        )
        logger.info("      %s...", hit["content_preview"].replace("\n", " "))
    time.sleep(0.15)
    return hits


def assert_all_game(hits: list[dict], expected_game: str, label: str) -> None:
    bad = [h for h in hits if h.get("game") != expected_game]
    if bad:
        raise AssertionError(f"{label}: expected only game={expected_game}, got {bad}")
    logger.info("PASS %s — all %d hits are game=%s", label, len(hits), expected_game)


def assert_all_weakness(hits: list[dict], expected: str, label: str) -> None:
    bad = [h for h in hits if h.get("weakness_category") != expected]
    if bad:
        raise AssertionError(
            f"{label}: expected weakness={expected}, got {[h.get('weakness_category') for h in bad]}"
        )
    logger.info("PASS %s — all hits weakness_category=%s", label, expected)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    _host_override()

    info = collection_info()
    logger.info("Collection: %s", info)
    if info["points_count"] == 0:
        raise SystemExit("Qdrant is empty — run scripts/ingest.py first")

    # 1) Game filter — CoD only
    cod_hits = run_query(
        "CoD loadout query stays in CoD",
        "best AR attachments compensator red dot loadout",
        game="cod",
        weakness_category="loadout",
    )
    assert_all_game(cod_hits, "cod", "cod_game_filter")
    assert_all_weakness(cod_hits, "loadout", "cod_loadout_filter")

    # 2) Game filter — Clash Royale decks
    cr_hits = run_query(
        "Clash Royale deck building",
        "positive elixir trade deck building cycle",
        game="cr",
        weakness_category="deck_building",
    )
    assert_all_game(cr_hits, "cr", "cr_game_filter")
    assert_all_weakness(cr_hits, "deck_building", "cr_deck_filter")

    # 3) Free Fire positioning / maps
    ff_hits = run_query(
        "Free Fire map positioning",
        "Bermuda rotation high ground safe zone",
        game="free_fire",
        weakness_category="positioning",
    )
    assert_all_game(ff_hits, "free_fire", "ff_game_filter")
    if ff_hits:
        assert_all_weakness(ff_hits, "positioning", "ff_positioning_filter")

    # 4) CoC base layout
    coc_hits = run_query(
        "CoC base layout",
        "town hall defense base layout farming war",
        game="coc",
        weakness_category="base_layout",
    )
    assert_all_game(coc_hits, "coc", "coc_game_filter")
    assert_all_weakness(coc_hits, "base_layout", "coc_layout_filter")

    # 5) skill_level filter (intermediate exists widely in corpus)
    skill_hits = run_query(
        "skill_level=intermediate filter on CoD",
        "perks and create a class multiplayer",
        game="cod",
        skill_level="intermediate",
        weakness_category="loadout",
    )
    assert_all_game(skill_hits, "cod", "skill_game_filter")
    bad_skill = [h for h in skill_hits if h.get("skill_level") != "intermediate"]
    if bad_skill:
        raise AssertionError(f"skill filter failed: {bad_skill}")
    logger.info("PASS skill_level filter — all intermediate")

    # 6) GTA money making
    gta_hits = run_query(
        "GTA Online money making",
        "CEO motorcycle club money making guide",
        game="gta_v_online",
        weakness_category="money_making",
    )
    assert_all_game(gta_hits, "gta_v_online", "gta_game_filter")
    assert_all_weakness(gta_hits, "money_making", "gta_money_filter")

    # 7) Negative control — wrong game filter should not leak CoD into CR
    leak_hits = run_query(
        "Negative: CR filter must not return CoD",
        "assault rifle compensator warzone loadout",
        game="cr",
        limit=5,
    )
    assert_all_game(leak_hits, "cr", "no_cod_leak_into_cr")

    logger.info("=" * 60)
    logger.info("All retrieval sanity checks passed")


if __name__ == "__main__":
    main()
