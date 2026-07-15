"""Step 4 — mastery plan generation (prompt build first; LLM call is Feature 2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.assessor import AssessmentResult
from app.agent.plan_prompt import (
    PLAN_EXAMPLE_JSON,
    PLAN_PROMPT_TEMPLATE,
    TONE_BY_EXPERIENCE,
)
from app.agent.retriever import ChunkResult

logger = logging.getLogger(__name__)

VALID_EXPERIENCE = ("new", "intermediate", "experienced")


def resolve_experience_level(context: dict[str, Any]) -> str:
    """Map profile experience_level to a known prompt register (default intermediate)."""
    profile = context.get("profile") or {}
    raw = (profile.get("experience_level") or "intermediate").strip().lower()
    if raw in VALID_EXPERIENCE:
        return raw
    # Soft aliases
    aliases = {
        "beginner": "new",
        "newbie": "new",
        "novice": "new",
        "advanced": "experienced",
        "expert": "experienced",
        "pro": "experienced",
    }
    return aliases.get(raw, "intermediate")


def _format_chunks_block(chunks: list[ChunkResult]) -> str:
    """Turn retrieved chunks into a numbered grounding block for the prompt."""
    if not chunks:
        return "(No strategy chunks retrieved — stay high-level and say grounding was limited.)"

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        preview = (chunk.content or "").strip()
        # Keep prompt bounded even if a chunk is long
        if len(preview) > 900:
            preview = preview[:900] + "…"
        parts.append(
            f"[{i}] id={chunk.chunk_id} "
            f"weakness={chunk.weakness_category} "
            f"skill={chunk.skill_level} "
            f"heading={chunk.heading}\n{preview}"
        )
    return "\n\n".join(parts)


def _format_rejection_block(rejection_reasons: list[str] | None) -> str:
    """Optional Day-11 block; empty string when no rejections."""
    if not rejection_reasons:
        return ""
    bullets = "\n".join(f"- {reason}" for reason in rejection_reasons if reason)
    if not bullets:
        return ""
    return (
        "\nREJECTION HISTORY (avoid repeating these):\n"
        f"{bullets}\n"
    )


def build_plan_prompt(
    context: dict[str, Any],
    assessment: AssessmentResult,
    chunks: list[ChunkResult],
    *,
    rejection_reasons: list[str] | None = None,
) -> str:
    """
    Build the Step-4 mastery plan prompt with experience-level tone branching.

    Takes: assembler context, AssessmentResult, retrieved ChunkResults,
           optional rejection reasons (wired fully on Day 11).
    Returns: prompt string for gemini.generate (Feature 2).
    Calls: nothing external (pure string assembly).
    """
    experience = resolve_experience_level(context)
    tone_block = TONE_BY_EXPERIENCE[experience]
    game_name = (context.get("game") or {}).get("name") or "unknown"

    slim_context = {
        "game": context.get("game"),
        "profile": context.get("profile"),
        "stats": context.get("stats"),
        "live": context.get("live"),
        "source": context.get("source"),
    }

    prompt = PLAN_PROMPT_TEMPLATE.format(
        tone_block=tone_block,
        game_name=game_name,
        player_context_json=json.dumps(slim_context, indent=2, default=str),
        assessment_json=json.dumps(assessment.to_dict(), indent=2),
        chunks_block=_format_chunks_block(chunks),
        rejection_block=_format_rejection_block(rejection_reasons),
        example_json=PLAN_EXAMPLE_JSON,
    )
    logger.info(
        "Built plan prompt experience=%s game=%s chunks=%d chars=%d",
        experience,
        game_name,
        len(chunks),
        len(prompt),
    )
    return prompt
