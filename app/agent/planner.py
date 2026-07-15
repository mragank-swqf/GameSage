"""Step 4 — mastery plan generation (prompt + Gemini JSON call + store)."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.assessor import AssessmentResult
from app.agent.plan_prompt import (
    PLAN_EXAMPLE_JSON,
    PLAN_PROMPT_TEMPLATE,
    TONE_BY_EXPERIENCE,
)
from app.agent.retriever import ChunkResult
from app.db.models import CoachingPlan
from app.services import gemini

logger = logging.getLogger(__name__)

VALID_EXPERIENCE = ("new", "intermediate", "experienced")
PLAN_TTL_DAYS = 7


class PlannerError(Exception):
    """Raised when plan generation fails after retries."""

    def __init__(self, message: str, *, step: str = "planner") -> None:
        super().__init__(message)
        self.step = step


@dataclass
class PlanResult:
    """Structured mastery plan — maps to coaching_plans JSONB columns."""

    skill_assessment: str
    seven_day_plan: list[dict[str, Any]]
    loadout_recommendations: list[dict[str, Any]]
    rank_roadmap: str
    experience_level: str
    fallback_used: bool = False
    raw_model_text: str | None = None
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    plan_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _strip_fences(text: str) -> str:
    """Remove optional ```json ... ``` wrappers."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return cleaned


def _normalize_day(entry: Any, expected_day: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"seven_day_plan[{expected_day - 1}] must be an object")
    missions = entry.get("missions") or []
    if not isinstance(missions, list) or not missions:
        raise ValueError(f"day {expected_day} needs a non-empty missions list")
    focus = str(entry.get("focus") or "").strip()
    if not focus:
        raise ValueError(f"day {expected_day} needs a focus string")
    return {
        "day": expected_day,
        "focus": focus,
        "missions": [str(m) for m in missions],
    }


def _normalize_loadout(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError("loadout entry must be an object")
    name = str(entry.get("name") or "").strip()
    if not name:
        raise ValueError("loadout needs a name")
    weapons = entry.get("weapons") or []
    perks = entry.get("perks") or []
    if not isinstance(weapons, list):
        weapons = [weapons]
    if not isinstance(perks, list):
        perks = [perks]
    return {
        "name": name,
        "weapons": [str(w) for w in weapons],
        "perks": [str(p) for p in perks],
        "playstyle_fit": str(entry.get("playstyle_fit") or ""),
        "reason": str(entry.get("reason") or ""),
    }


def _parse_plan(
    raw: str,
    *,
    experience_level: str,
    chunk_ids: list[str],
) -> PlanResult:
    """Parse + validate model JSON into PlanResult."""
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, dict):
        raise ValueError("Plan JSON must be an object")

    skill_assessment = str(data.get("skill_assessment") or "").strip()
    if not skill_assessment:
        raise ValueError("skill_assessment is required")

    days_raw = data.get("seven_day_plan")
    if not isinstance(days_raw, list) or len(days_raw) != 7:
        raise ValueError("seven_day_plan must be a list of exactly 7 days")
    seven_day_plan = [_normalize_day(days_raw[i], i + 1) for i in range(7)]

    loadouts_raw = data.get("loadout_recommendations")
    if not isinstance(loadouts_raw, list) or not loadouts_raw:
        raise ValueError("loadout_recommendations must be a non-empty list")
    loadouts = [_normalize_loadout(item) for item in loadouts_raw]

    rank_roadmap = str(data.get("rank_roadmap") or "").strip()
    if not rank_roadmap:
        raise ValueError("rank_roadmap is required")

    return PlanResult(
        skill_assessment=skill_assessment,
        seven_day_plan=seven_day_plan,
        loadout_recommendations=loadouts,
        rank_roadmap=rank_roadmap,
        experience_level=experience_level,
        fallback_used=False,
        raw_model_text=raw,
        retrieved_chunk_ids=list(chunk_ids),
    )


async def store_plan(
    db: AsyncSession,
    context: dict[str, Any],
    assessment: AssessmentResult,
    plan: PlanResult,
) -> CoachingPlan:
    """
    Persist a PlanResult to coaching_plans (including chunk audit trail).

    Takes: DB session, assembler context, assessment, PlanResult from generate_plan.
    Returns: saved CoachingPlan row (with id).
    Calls: Postgres insert on coaching_plans.
    """
    user_id = context.get("user_id")
    game_id = context.get("game_id")
    if user_id is None or game_id is None:
        raise PlannerError("context.user_id and context.game_id are required to store a plan")

    now = datetime.now(timezone.utc)
    row = CoachingPlan(
        user_id=int(user_id),
        game_id=int(game_id),
        skill_assessment=plan.skill_assessment,
        identified_weaknesses={
            "weaknesses": assessment.weaknesses,
            "skill_tier": assessment.skill_tier,
            "priority_focus": assessment.priority_focus,
        },
        retrieved_chunk_ids=list(plan.retrieved_chunk_ids),
        seven_day_plan={"days": plan.seven_day_plan},
        loadout_recommendations={"loadouts": plan.loadout_recommendations},
        rank_roadmap=plan.rank_roadmap,
        generated_at=now,
        expires_at=now + timedelta(days=PLAN_TTL_DAYS),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info(
        "Stored coaching plan id=%s user=%s game=%s chunks=%d expires=%s",
        row.id,
        row.user_id,
        row.game_id,
        len(plan.retrieved_chunk_ids),
        row.expires_at.isoformat() if row.expires_at else None,
    )
    return row


async def generate_plan(
    context: dict[str, Any],
    assessment: AssessmentResult,
    chunks: list[ChunkResult],
    db: AsyncSession | None = None,
    *,
    rejection_reasons: list[str] | None = None,
    persist: bool = False,
) -> PlanResult:
    """
    Run Step 4 mastery plan generation.

    Takes: assembler context, assessment, retrieved chunks; optional db + persist.
    Returns: PlanResult (with plan_id set when persist=True).
    Calls: gemini.generate (retry once); store_plan when persist and db given.
    """
    experience = resolve_experience_level(context)
    chunk_ids = [c.chunk_id for c in chunks]
    prompt = build_plan_prompt(
        context,
        assessment,
        chunks,
        rejection_reasons=rejection_reasons,
    )
    started = time.perf_counter()

    last_error: Exception | None = None
    result: PlanResult | None = None
    for attempt in range(1, 3):
        try:
            raw = gemini.generate(prompt)
            result = _parse_plan(
                raw,
                experience_level=experience,
                chunk_ids=chunk_ids,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Plan ok attempt=%s experience=%s days=%d loadouts=%d (%.0fms)",
                attempt,
                experience,
                len(result.seven_day_plan),
                len(result.loadout_recommendations),
                elapsed_ms,
            )
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Plan parse/generate failed attempt=%s: %s", attempt, exc
            )

    if result is None:
        raise PlannerError(
            f"Plan generation failed after retries: {last_error}"
        ) from last_error

    if persist:
        if db is None:
            raise PlannerError("persist=True requires a db session")
        row = await store_plan(db, context, assessment, result)
        result.plan_id = row.id
    return result
