"""Step 2 — skill assessment via Gemini (constrained taxonomy JSON)."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.assessment_prompt import (
    ASSESSMENT_EXAMPLE_JSON,
    ASSESSMENT_PROMPT_TEMPLATE,
)
from app.agent.taxonomy import (
    filter_valid_weaknesses,
    format_weaknesses_for_prompt,
    get_weaknesses_for_game,
    map_topic_to_weakness,
)
from app.services import gemini

logger = logging.getLogger(__name__)

ALLOWED_SKILL_TIERS = ("beginner", "intermediate", "advanced", "master")


class AssessorError(Exception):
    """Raised when assessment cannot be produced even after fallback."""

    def __init__(self, message: str, *, step: str = "assessor") -> None:
        super().__init__(message)
        self.step = step


@dataclass
class AssessmentResult:
    """Structured output of Step 2 — drives Qdrant filters in Step 3."""

    weaknesses: list[str]
    skill_tier: str
    priority_focus: str
    fallback_used: bool = False
    raw_model_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_fences(text: str) -> str:
    """Remove optional ```json ... ``` wrappers Gemini sometimes adds."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return cleaned


def build_assessment_prompt(context: dict[str, Any]) -> str:
    """
    Fill the Feature-4 assessment template with player context + taxonomy.

    Takes: unified context from assemble_context.
    Returns: prompt string for gemini.generate.
    Calls: taxonomy.format_weaknesses_for_prompt (no LLM).
    """
    game = context.get("game") or {}
    game_name = game.get("name") or ""

    slim = {
        "game": game,
        "profile": context.get("profile"),
        "stats": context.get("stats"),
        "live": context.get("live"),
        "source": context.get("source"),
    }
    return ASSESSMENT_PROMPT_TEMPLATE.format(
        allowed_weaknesses=format_weaknesses_for_prompt(game_name),
        skill_tiers=", ".join(ALLOWED_SKILL_TIERS),
        player_context_json=json.dumps(slim, indent=2, default=str),
        example_json=ASSESSMENT_EXAMPLE_JSON,
    )


def _parse_assessment(raw: str, game_name: str) -> AssessmentResult:
    """Parse + validate model JSON into AssessmentResult. Raises ValueError on bad shape."""
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, dict):
        raise ValueError("Assessment JSON must be an object")

    weaknesses_raw = data.get("weaknesses") or []
    if not isinstance(weaknesses_raw, list):
        raise ValueError("weaknesses must be a list")

    weaknesses = filter_valid_weaknesses(
        game_name, [str(w) for w in weaknesses_raw]
    )
    if not weaknesses:
        raise ValueError("No valid taxonomy weaknesses in model output")

    skill_tier = str(data.get("skill_tier") or "").strip().lower()
    if skill_tier not in ALLOWED_SKILL_TIERS:
        raise ValueError(f"Invalid skill_tier: {skill_tier}")

    priority = str(data.get("priority_focus") or "").strip().lower()
    if priority not in weaknesses:
        priority = weaknesses[0]

    return AssessmentResult(
        weaknesses=weaknesses,
        skill_tier=skill_tier,
        priority_focus=priority,
        fallback_used=False,
        raw_model_text=raw,
    )


def _fallback_assessment(context: dict[str, Any]) -> AssessmentResult:
    """
    Hard fallback when Gemini JSON fails twice.

    Uses known_weaknesses from stats (mapped through taxonomy) + defaults.
    """
    game_name = (context.get("game") or {}).get("name") or ""
    stats = context.get("stats") or {}
    known = stats.get("known_weaknesses") or []

    mapped: list[str] = []
    for item in known:
        text = str(item).strip()
        as_label = filter_valid_weaknesses(game_name, [text])
        if as_label:
            mapped.extend(as_label)
            continue
        topic_hit = map_topic_to_weakness(text, game_name)
        if topic_hit:
            mapped.append(topic_hit)

    mapped = filter_valid_weaknesses(game_name, mapped)

    if not mapped:
        # Last resort: first 2 taxonomy labels for the game
        mapped = get_weaknesses_for_game(game_name)[:2]

    if not mapped:
        raise AssessorError("No weaknesses available for fallback assessment")

    # Rough tier from profile experience_level if present
    exp = ((context.get("profile") or {}).get("experience_level") or "").lower()
    tier_map = {
        "new": "beginner",
        "intermediate": "intermediate",
        "experienced": "advanced",
    }
    skill_tier = tier_map.get(exp, "intermediate")

    return AssessmentResult(
        weaknesses=mapped[:2],
        skill_tier=skill_tier,
        priority_focus=mapped[0],
        fallback_used=True,
        raw_model_text=None,
    )


async def assess(
    context: dict[str, Any],
    db: AsyncSession | None = None,
) -> AssessmentResult:
    """
    Run Step 2 skill assessment.

    Takes: player context dict from assemble_context; db reserved for later use.
    Returns: AssessmentResult with weaknesses, skill_tier, priority_focus.
    Calls: Gemini generate (retry once on JSON parse failure); taxonomy filter.

    On double parse failure, falls back to known_weaknesses / taxonomy defaults.
    """
    _ = db  # reserved for future assessment persistence
    game_name = (context.get("game") or {}).get("name") or ""
    if not game_name:
        raise AssessorError("context.game.name is required")

    prompt = build_assessment_prompt(context)
    started = time.perf_counter()

    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            raw = gemini.generate(prompt)
            result = _parse_assessment(raw, game_name)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Assessment ok attempt=%s game=%s weaknesses=%s tier=%s (%.0fms)",
                attempt,
                game_name,
                result.weaknesses,
                result.skill_tier,
                elapsed_ms,
            )
            return result
        except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
            last_error = exc
            logger.warning(
                "Assessment parse/generate failed attempt=%s: %s", attempt, exc
            )

    logger.error(
        "Assessment falling back after retries: %s", last_error
    )
    result = _fallback_assessment(context)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Assessment fallback game=%s weaknesses=%s (%.0fms)",
        game_name,
        result.weaknesses,
        elapsed_ms,
    )
    return result
