"""Retag chunks.jsonl weakness_category from topic using the taxonomy map."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Allow `python scripts/tag_weaknesses.py` to import app.*
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.taxonomy import (  # noqa: E402
    is_valid_weakness,
    map_topic_to_weakness,
)

logger = logging.getLogger(__name__)

CHUNKS_PATH = ROOT / "data" / "chunks.jsonl"


def tag_chunks(path: Path = CHUNKS_PATH) -> dict[str, int]:
    """Rewrite chunks with taxonomy-mapped weakness_category. Returns stats."""
    if not path.exists():
        raise FileNotFoundError(f"Run chunker first — missing {path}")

    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    updated = 0
    unchanged = 0
    unmapped: dict[str, int] = {}
    invalid: dict[str, int] = {}

    for row in rows:
        topic = str(row.get("topic", ""))
        game = str(row.get("game", ""))
        mapped = map_topic_to_weakness(topic, game=game)

        if mapped is None:
            unmapped[topic] = unmapped.get(topic, 0) + 1
            unchanged += 1
            continue

        if not is_valid_weakness(game, mapped):
            key = f"{game}:{mapped}"
            invalid[key] = invalid.get(key, 0) + 1
            logger.warning(
                "Mapped weakness %r not valid for game %r (topic=%r) — leaving as-is",
                mapped,
                game,
                topic,
            )
            unchanged += 1
            continue

        old = row.get("weakness_category")
        row["weakness_category"] = mapped
        if old != mapped:
            updated += 1
            logger.debug(
                "%s: %s → %s (topic=%s)",
                row.get("chunk_id"),
                old,
                mapped,
                topic,
            )
        else:
            unchanged += 1

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if unmapped:
        logger.warning("Unmapped topics (manual review):")
        for topic, count in sorted(unmapped.items(), key=lambda x: -x[1]):
            logger.warning("  %r — %d chunk(s)", topic, count)
    else:
        logger.info("All topics mapped to taxonomy weakness categories")

    if invalid:
        logger.warning("Invalid genre/weakness combos: %s", invalid)

    logger.info(
        "Done — updated: %d, unchanged: %d, total: %d",
        updated,
        unchanged,
        len(rows),
    )
    return {
        "updated": updated,
        "unchanged": unchanged,
        "unmapped_topics": len(unmapped),
        "total": len(rows),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    tag_chunks()


if __name__ == "__main__":
    main()
