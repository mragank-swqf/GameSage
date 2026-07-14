"""Assessment prompt template — Step 2 skill assessment (Feature 4).

Tune this string when plans are wrong; keep assessor.py focused on call/parse/retry.
"""

from __future__ import annotations

# Placeholders filled by build_assessment_prompt():
#   {allowed_weaknesses}  — taxonomy labels for this game
#   {skill_tiers}         — allowed skill_tier enum
#   {player_context_json} — slim assembler context as JSON
#   {example_json}        — one-shot format anchor
ASSESSMENT_PROMPT_TEMPLATE = """You are GameSage's skill assessment engine for a game mastery agent.
Given the player's context, identify their main skill weaknesses so we can retrieve the right strategy content.

RULES:
- Pick weakness labels ONLY from this allowed list for this game: {allowed_weaknesses}
- Pick skill_tier ONLY from: {skill_tiers}
- priority_focus must be exactly one of the weaknesses you listed
- Prefer 2 weaknesses (minimum 1, maximum 3)
- Use live API data when present (e.g. trophies, town hall, heroes, arena) plus goals and known_weaknesses
- Be specific to this player's state — do not invent labels outside the allowed list
- Return ONLY valid JSON, no preamble, no markdown fences

PLAYER CONTEXT:
{player_context_json}

Example output (shape only — labels must still come from the allowed list above):
{example_json}
"""

# Genre-agnostic shape anchor. Labels in the example are illustrative;
# the RULES block forces the model onto the real allowed list.
ASSESSMENT_EXAMPLE_JSON = (
    '{"weaknesses":["troop_deployment","base_layout"],'
    '"skill_tier":"advanced",'
    '"priority_focus":"troop_deployment"}'
)
