"""Gemini client — embeddings + generation (google.genai SDK)."""

from __future__ import annotations

import logging
import os
import time
from typing import List

from dotenv import load_dotenv
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Embedding model (API no longer serves text-embedding-004 on free tier)
EMBEDDING_MODEL = "gemini-embedding-001"
GENERATION_MODEL = "gemini-2.5-flash-lite"
EMBED_BATCH_DELAY_SECONDS = 0.1  # 100ms between embedding calls
EXPECTED_DIM = 768

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Load API key and return a shared Gemini client."""
    global _client
    if _client is not None:
        return _client

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise RuntimeError("GEMINI_API_KEY is missing or unset in .env")

    _client = genai.Client(api_key=api_key)
    logger.info("Gemini client configured")
    return _client


def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
    """
    Embed text with gemini-embedding-001.

    Returns a 768-dim float vector (output_dimensionality=768) for Qdrant.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Cannot embed empty text")

    client = _get_client()
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=cleaned,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EXPECTED_DIM,
            ),
        )
    except Exception:
        logger.exception("Gemini embedding failed")
        raise

    if not result.embeddings:
        raise ValueError("Gemini returned no embeddings")

    embedding = list(result.embeddings[0].values)
    if len(embedding) != EXPECTED_DIM:
        raise ValueError(
            f"Expected {EXPECTED_DIM}-dim embedding, got {len(embedding)}"
        )
    return embedding


def embed_texts(
    texts: list[str],
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Embed many texts with a short delay between calls (rate-limit friendly)."""
    vectors: list[list[float]] = []
    for i, text in enumerate(texts):
        vectors.append(embed_text(text, task_type=task_type))
        if i < len(texts) - 1:
            time.sleep(EMBED_BATCH_DELAY_SECONDS)
    return vectors


def generate(prompt: str) -> str:
    """
    Generate text with gemini-2.5-flash-lite.

    Used later by assessor / planner. Callers should ask for JSON-only output.
    """
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("Cannot generate from empty prompt")

    client = _get_client()
    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=cleaned,
        )
    except Exception:
        logger.exception("Gemini generation failed")
        raise

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Gemini returned empty generation")
    return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = "SMG loadout tips for close-range Call of Duty fights"
    vector = embed_text(sample)
    print(f"embed_model={EMBEDDING_MODEL}")
    print(f"dims={len(vector)} first3={vector[:3]}")
