from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssessRequest(BaseModel):
    """Optional body for POST /players/{id}/assess/{game_id}."""

    player_tag: Optional[str] = Field(
        None,
        examples=["#P28JPGRLJ"],
        description="CoC/CR player tag for live merge (overrides profile notes).",
    )
    skip_live: bool = Field(
        False,
        description="If true, skip CoC/CR live API merge (safer for demos).",
    )


class AssessmentSummary(BaseModel):
    weaknesses: list[str]
    skill_tier: str
    priority_focus: str
    fallback_used: bool = False


class MissionDay(BaseModel):
    day: int
    focus: str
    missions: list[str]


class LoadoutCard(BaseModel):
    name: str
    weapons: list[str] = Field(default_factory=list)
    perks: list[str] = Field(default_factory=list)
    playstyle_fit: str = ""
    reason: str = ""


class AssessResponse(BaseModel):
    """Full pipeline result: assessment + stored mastery plan."""

    plan_id: int
    user_id: int
    game_id: int
    assessment: AssessmentSummary
    skill_assessment: str
    seven_day_plan: list[MissionDay]
    loadout_recommendations: list[LoadoutCard]
    rank_roadmap: str
    experience_level: str
    retrieved_chunk_ids: list[str]
    chunk_count: int
    fallback_used: bool = Field(
        ...,
        description="True if assessment soft-fallback or retrieval returned 0 chunks.",
    )
    generated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class PlayerStatsCreate(BaseModel):
    game_id: int = Field(..., examples=[3], description="FK to games.id")
    current_rank: Optional[str] = Field(None, max_length=50, examples=["gold"])
    kd_ratio: Optional[float] = Field(None, examples=[0.95])
    win_rate: Optional[float] = Field(None, examples=[42.0])
    weekly_playtime_hours: Optional[float] = Field(None, examples=[8.5])
    preferred_weapons: Optional[list[str]] = Field(
        None, examples=[["smg", "assault_rifle"]]
    )
    known_weaknesses: Optional[list[str]] = Field(
        None, examples=[["I lose mid-range AR fights"]]
    )
    goals: Optional[list[str]] = Field(None, examples=[["reach platinum"]])


class PlayerStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    game_id: int
    current_rank: Optional[str] = None
    kd_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    weekly_playtime_hours: Optional[float] = None
    preferred_weapons: Optional[list[str]] = None
    known_weaknesses: Optional[list[str]] = None
    goals: Optional[list[str]] = None
    source: str
    submitted_at: datetime
