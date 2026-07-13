from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    genre: str
    supported_modes: Optional[list[str]] = None
    has_live_api: bool
    created_at: datetime


class GameTopicsResponse(BaseModel):
    game_id: int
    game: str
    display_name: str
    topics: list[str] = Field(
        ...,
        description="Distinct weakness_category values present in Qdrant for this game.",
        examples=[["positioning", "aim", "loadout"]],
    )
