"""Qdrant client — collection setup and vector search helpers."""

from __future__ import annotations

import logging
import os
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)

COLLECTION_NAME = "game_strategies"
VECTOR_SIZE = 768  # gemini-embedding-001 with output_dimensionality=768
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


def build_filter(
    *,
    game: str | None = None,
    weakness_category: str | None = None,
    skill_level: str | None = None,
    experience_level: str | None = None,
    weapon_class: str | None = None,
) -> qmodels.Filter | None:
    """Build a Qdrant payload filter. game should almost always be set."""
    must: list[qmodels.FieldCondition] = []
    fields = {
        "game": game,
        "weakness_category": weakness_category,
        "skill_level": skill_level,
        "experience_level": experience_level,
        "weapon_class": weapon_class,
    }
    for key, value in fields.items():
        if value:
            must.append(
                qmodels.FieldCondition(
                    key=key,
                    match=qmodels.MatchValue(value=value),
                )
            )
    if not must:
        return None
    return qmodels.Filter(must=must)


def search(
    query_vector: list[float],
    *,
    game: str,
    weakness_category: str | None = None,
    skill_level: str | None = None,
    experience_level: str | None = None,
    weapon_class: str | None = None,
    limit: int = 5,
    client: QdrantClient | None = None,
) -> list[dict[str, Any]]:
    """
    Vector search with required game filter (+ optional metadata filters).

    Returns list of {chunk_id, score, content, ...payload}.
    """
    client = client or get_qdrant_client()
    query_filter = build_filter(
        game=game,
        weakness_category=weakness_category,
        skill_level=skill_level,
        experience_level=experience_level,
        weapon_class=weapon_class,
    )

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    hits: list[dict[str, Any]] = []
    for point in response.points:
        payload = point.payload or {}
        content = payload.get("content") or ""
        hits.append(
            {
                "chunk_id": payload.get("chunk_id"),
                "score": point.score,
                "game": payload.get("game"),
                "weakness_category": payload.get("weakness_category"),
                "skill_level": payload.get("skill_level"),
                "experience_level": payload.get("experience_level"),
                "topic": payload.get("topic"),
                "heading": payload.get("heading"),
                "content": content,
                "content_preview": content[:180],
            }
        )
    return hits


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


def list_weakness_categories_for_game(
    game: str,
    client: QdrantClient | None = None,
) -> list[str]:
    """Return sorted unique weakness_category values stored for a game in Qdrant."""
    client = client or get_qdrant_client()
    query_filter = build_filter(game=game)
    categories: set[str] = set()
    offset: Any = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=query_filter,
            limit=128,
            offset=offset,
            with_payload=["weakness_category"],
            with_vectors=False,
        )
        for point in points:
            value = (point.payload or {}).get("weakness_category")
            if value:
                categories.add(str(value))
        if next_offset is None:
            break
        offset = next_offset

    return sorted(categories)


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
