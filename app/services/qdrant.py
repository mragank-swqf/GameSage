"""Qdrant client — collection setup and vector search helpers."""

from __future__ import annotations

import logging
import os
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)

COLLECTION_NAME = "game_strategies"
VECTOR_SIZE = 768  # Gemini text-embedding-004
DISTANCE = qmodels.Distance.COSINE

PAYLOAD_INDEX_FIELDS = (
    "game",
    "genre",
    "skill_level",
    "weakness_category",
    "weapon_class",
    "experience_level",
)


def get_qdrant_client() -> QdrantClient:
    """Build a Qdrant client from env (host/port)."""
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def ensure_collection(client: QdrantClient | None = None) -> None:
    """Create game_strategies collection + payload indexes if missing."""
    client = client or get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}

    if COLLECTION_NAME not in existing:
        logger.info(
            "Creating collection %s (size=%d, distance=%s)",
            COLLECTION_NAME,
            VECTOR_SIZE,
            DISTANCE,
        )
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_SIZE,
                distance=DISTANCE,
            ),
        )
    else:
        logger.info("Collection %s already exists", COLLECTION_NAME)

    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            logger.info("Payload index ready: %s", field)
        except Exception as exc:
            # Index may already exist — Qdrant raises if duplicate
            logger.info("Payload index %s — %s", field, exc)


def collection_info(client: QdrantClient | None = None) -> dict[str, Any]:
    """Return basic collection stats for sanity checks."""
    client = client or get_qdrant_client()
    info = client.get_collection(COLLECTION_NAME)
    return {
        "name": COLLECTION_NAME,
        "points_count": info.points_count,
        "status": str(info.status),
        "vector_size": VECTOR_SIZE,
        "distance": str(DISTANCE),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()
    # Host machine talks to published port — override Docker hostname if needed
    if os.getenv("QDRANT_HOST") == "qdrant":
        os.environ["QDRANT_HOST"] = "localhost"
        logger.info("QDRANT_HOST=qdrant not reachable from host — using localhost")

    ensure_collection()
    print(collection_info())
