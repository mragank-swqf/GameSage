"""Step 3 — weakness-conditioned RAG retrieval (one Qdrant query per weakness)."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from qdrant_client import QdrantClient

from app.agent.assessor import AssessmentResult
from app.services import gemini, qdrant as qdrant_service

logger = logging.getLogger(__name__)

CHUNKS_PER_WEAKNESS = 5
MAX_CHUNKS = 15  # planner context budget — never send more than this


@dataclass
class ChunkResult:
    """One retrieved strategy chunk for plan grounding."""

    chunk_id: str
    score: float
    content: str
    game: str | None
    weakness_category: str | None
    skill_level: str | None
    experience_level: str | None
    topic: str | None
    heading: str | None
    weakness_queried: str  # which assessment weakness triggered this hit

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _query_text(game_name: str, weakness: str) -> str:
    """
    Build the embedding query from assessment output — not a raw user question.

    Interview talking point: retrieval is conditioned on agent reasoning.
    """
    readable = weakness.replace("_", " ")
    return f"{game_name} gameplay strategy to improve {readable}"


def merge_and_dedupe_chunks(
    chunks: list[ChunkResult],
    *,
    max_chunks: int = MAX_CHUNKS,
) -> list[ChunkResult]:
    """
    Merge per-weakness hits: keep best score per chunk_id, sort desc, cap length.

    Takes: flat list from one-or-more weakness searches.
    Returns: deduped, score-sorted list with at most max_chunks items.
    Calls: nothing external.
    """
    best_by_id: dict[str, ChunkResult] = {}
    for chunk in chunks:
        existing = best_by_id.get(chunk.chunk_id)
        if existing is None or chunk.score > existing.score:
            best_by_id[chunk.chunk_id] = chunk

    merged = sorted(best_by_id.values(), key=lambda c: c.score, reverse=True)
    capped = merged[:max_chunks]
    logger.info(
        "Merge/dedupe: in=%d unique=%d out=%d (cap=%d)",
        len(chunks),
        len(merged),
        len(capped),
        max_chunks,
    )
    return capped


def retrieve(
    assessment: AssessmentResult,
    context: dict[str, Any],
    qdrant_client: QdrantClient | None = None,
) -> list[ChunkResult]:
    """
    Run weakness-conditioned retrieval for each assessed weakness.

    Takes: AssessmentResult from Step 2, player context from Step 1, optional Qdrant client.
    Returns: deduped, score-sorted ChunkResult list capped at MAX_CHUNKS.
    Calls: gemini.embed_text (query vector), qdrant.search (filtered ANN).
    """
    game = context.get("game") or {}
    game_name = game.get("name") or ""
    if not game_name:
        raise ValueError("context.game.name is required for retrieval")

    profile = context.get("profile") or {}
    experience_level = profile.get("experience_level")
    skill_level = assessment.skill_tier

    client = qdrant_client or qdrant_service.get_qdrant_client()
    started = time.perf_counter()
    results: list[ChunkResult] = []

    for weakness in assessment.weaknesses:
        query = _query_text(game_name, weakness)
        vector = gemini.embed_text(query, task_type="RETRIEVAL_QUERY")
        hits = qdrant_service.search(
            vector,
            game=game_name,
            weakness_category=weakness,
            skill_level=skill_level,
            experience_level=experience_level,
            limit=CHUNKS_PER_WEAKNESS,
            client=client,
        )
        logger.info(
            "Retrieval weakness=%s game=%s skill=%s exp=%s hits=%d",
            weakness,
            game_name,
            skill_level,
            experience_level,
            len(hits),
        )
        for hit in hits:
            chunk_id = hit.get("chunk_id") or ""
            if not chunk_id:
                continue
            results.append(
                ChunkResult(
                    chunk_id=str(chunk_id),
                    score=float(hit.get("score") or 0.0),
                    content=str(hit.get("content") or ""),
                    game=hit.get("game"),
                    weakness_category=hit.get("weakness_category"),
                    skill_level=hit.get("skill_level"),
                    experience_level=hit.get("experience_level"),
                    topic=hit.get("topic"),
                    heading=hit.get("heading"),
                    weakness_queried=weakness,
                )
            )

    merged = merge_and_dedupe_chunks(results)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Retrieval done game=%s weaknesses=%d chunks=%d (%.0fms)",
        game_name,
        len(assessment.weaknesses),
        len(merged),
        elapsed_ms,
    )
    return merged
