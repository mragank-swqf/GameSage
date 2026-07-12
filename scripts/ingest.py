"""Embed chunks.jsonl and upsert vectors + payload into Qdrant."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client.http import models as qmodels

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.gemini import embed_text  # noqa: E402
from app.services.qdrant import (  # noqa: E402
    COLLECTION_NAME,
    collection_info,
    ensure_collection,
    get_qdrant_client,
)

logger = logging.getLogger(__name__)

CHUNKS_PATH = ROOT / "data" / "chunks.jsonl"
UPSERT_BATCH_SIZE = 25
POINT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace


def _host_qdrant_override() -> None:
    """When running on the host, Docker service name 'qdrant' is not resolvable."""
    if os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"
        logger.info("QDRANT_HOST=qdrant → using localhost for host-side ingest")


def _point_id(chunk_id: str) -> str:
    """Stable UUID from chunk_id so re-ingest overwrites the same point."""
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


def _payload_from_chunk(chunk: dict) -> dict:
    return {
        "chunk_id": chunk["chunk_id"],
        "content": chunk["content"],
        "game": chunk.get("game", ""),
        "genre": chunk.get("genre", ""),
        "mode": chunk.get("mode", ""),
        "topic": chunk.get("topic", ""),
        "weakness_category": chunk.get("weakness_category", ""),
        "skill_level": chunk.get("skill_level", ""),
        "weapon_class": chunk.get("weapon_class", "any"),
        "experience_level": chunk.get("experience_level", ""),
        "source": chunk.get("source", ""),
        "heading": chunk.get("heading", ""),
    }


def load_chunks(path: Path = CHUNKS_PATH, game: str | None = None) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — run chunker.py first")

    chunks: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if game and row.get("game") != game:
                continue
            chunks.append(row)
    return chunks


def ingest_chunks(chunks: list[dict]) -> dict[str, int]:
    """Embed + upsert all chunks. Returns per-game counts."""
    client = get_qdrant_client()
    ensure_collection(client)

    by_game: dict[str, int] = {}
    batch: list[qmodels.PointStruct] = []
    total = len(chunks)

    for i, chunk in enumerate(chunks, start=1):
        chunk_id = chunk["chunk_id"]
        game = chunk.get("game", "unknown")
        content = chunk.get("content", "").strip()
        if not content:
            logger.warning("Skipping empty chunk %s", chunk_id)
            continue

        logger.info("[%d/%d] Embedding %s", i, total, chunk_id)
        try:
            vector = embed_text(content)
        except Exception:
            logger.exception("Embed failed for %s — retrying once", chunk_id)
            time.sleep(2.0)
            try:
                vector = embed_text(content)
            except Exception:
                logger.exception("Embed failed for %s — skipping", chunk_id)
                continue

        batch.append(
            qmodels.PointStruct(
                id=_point_id(chunk_id),
                vector=vector,
                payload=_payload_from_chunk(chunk),
            )
        )
        by_game[game] = by_game.get(game, 0) + 1
        time.sleep(0.1)  # respect free-tier embedding rate limits

        if len(batch) >= UPSERT_BATCH_SIZE or i == total:
            client.upsert(collection_name=COLLECTION_NAME, points=batch)
            logger.info("Upserted batch of %d (progress %d/%d)", len(batch), i, total)
            batch = []

    return by_game


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    _host_qdrant_override()

    game = sys.argv[1] if len(sys.argv) > 1 else None
    chunks = load_chunks(game=game)
    logger.info("Loaded %d chunks%s", len(chunks), f" (game={game})" if game else "")

    counts = ingest_chunks(chunks)
    for g, n in sorted(counts.items()):
        logger.info("  %s: %d points", g, n)

    info = collection_info()
    logger.info("Qdrant collection status: %s", info)


if __name__ == "__main__":
    main()
