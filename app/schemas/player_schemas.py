from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
