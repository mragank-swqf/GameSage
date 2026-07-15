"""Plan generation prompts — Step 4 mastery plan (Day 7 Feature 1).

Same grounding blocks for everyone; experience_level only changes TONE / depth.
Tune strings here; keep planner.py focused on call/parse/store later.
"""

from __future__ import annotations

# Shared JSON shape for all experience levels
PLAN_EXAMPLE_JSON = """{
  "skill_assessment": "One short paragraph summarizing current level and main gaps.",
  "seven_day_plan": [
    {"day": 1, "focus": "primary focus for the day", "missions": ["concrete practice 1", "concrete practice 2"]},
    {"day": 2, "focus": "...", "missions": ["...", "..."]},
    {"day": 3, "focus": "...", "missions": ["...", "..."]},
    {"day": 4, "focus": "...", "missions": ["...", "..."]},
    {"day": 5, "focus": "...", "missions": ["...", "..."]},
    {"day": 6, "focus": "...", "missions": ["...", "..."]},
    {"day": 7, "focus": "...", "missions": ["...", "..."]}
  ],
  "loadout_recommendations": [
    {
      "name": "loadout or attack/deck name",
      "weapons": ["item or troop 1", "item or troop 2"],
      "perks": ["perk, spell, or card note"],
      "playstyle_fit": "why this fits the player",
      "reason": "grounded in retrieved strategy chunks"
    }
  ],
  "rank_roadmap": "Path from current rank/level toward the player's goals, with milestones."
}"""

# Tone-only instructions (injected into the shared template)
TONE_BY_EXPERIENCE: dict[str, str] = {
    "new": (
        "EXPERIENCE REGISTER — NEW PLAYER:\n"
        "- Explain jargon briefly the first time you use it.\n"
        "- Prefer forgiving, simple setups over advanced optimizations.\n"
        "- Keep missions short and doable; define unclear game terms in one clause.\n"
        "- Encouraging but concrete — no empty pep talk."
    ),
    "intermediate": (
        "EXPERIENCE REGISTER — INTERMEDIATE:\n"
        "- Balanced tone: assume basic game knowledge, light jargon OK.\n"
        "- Mix fundamentals refreshers with one stretch goal per day.\n"
        "- Be specific; skip absolute beginner hand-holding."
    ),
    "experienced": (
        "EXPERIENCE REGISTER — EXPERIENCED:\n"
        "- Terse. Assume full game knowledge — no glossary, no hand-holding.\n"
        "- Optimize for efficiency and competitive edge.\n"
        "- Dense missions; skip fluff and obvious tips."
    ),
}

# Placeholders filled by build_plan_prompt():
#   {tone_block} {game_name} {player_context_json} {assessment_json}
#   {chunks_block} {rejection_block} {example_json}
PLAN_PROMPT_TEMPLATE = """You are GameSage's mastery plan engine.
Build a personalized 7-day mastery plan for this player grounded ONLY in the retrieved strategy chunks
plus their profile/stats/assessment. Do not invent mechanics not supported by the chunks.

{tone_block}

GAME: {game_name}

RULES:
- Return ONLY valid JSON, no preamble, no markdown fences
- seven_day_plan MUST have exactly 7 objects, days 1 through 7
- Each day needs a clear focus and 1-3 concrete missions
- loadout_recommendations: 1-3 entries adapted to this game
  (shooter = guns/perks; strategy = troops/deck/spells; open_world = approach/gear)
- Ground recommendations in the RETRIEVED CHUNKS (cite ideas, not chunk ids in prose)
- Align the plan with assessed weaknesses and priority_focus
- If a rejection history block is present, avoid repeating those suggestions

PLAYER CONTEXT:
{player_context_json}

ASSESSMENT:
{assessment_json}

RETRIEVED STRATEGY CHUNKS:
{chunks_block}
{rejection_block}

Example output shape:
{example_json}
"""
