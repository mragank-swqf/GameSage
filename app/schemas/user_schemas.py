from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ExperienceLevel = Literal["new", "intermediate", "experienced"]


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, examples=["mragank"])
    email: EmailStr = Field(..., examples=["mragank@example.com"])


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    created_at: datetime


class UserProfileCreate(BaseModel):
    game_id: int = Field(..., examples=[3], description="FK to games.id")
    experience_level: Optional[ExperienceLevel] = Field(
        None, examples=["intermediate"]
    )
    preferred_playstyle: Optional[str] = Field(
        None, max_length=50, examples=["aggressive"]
    )
    notes: Optional[str] = Field(
        None, examples=["Prefer SMG / close-mid range only"]
    )


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    game_id: int
    experience_level: Optional[str] = None
    preferred_playstyle: Optional[str] = None
    notes: Optional[str] = None
    updated_at: datetime
