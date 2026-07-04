from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    genre: Mapped[str] = mapped_column(String(50), nullable=False)
    supported_modes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    has_live_api: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    experience_level: Mapped[Optional[str]] = mapped_column(String(20))
    preferred_playstyle: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlayerStat(Base):
    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    current_rank: Mapped[Optional[str]] = mapped_column(String(50))
    kd_ratio: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    win_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    weekly_playtime_hours: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    preferred_weapons: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    known_weaknesses: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    goals: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    source: Mapped[str] = mapped_column(String(20), default="user_submitted", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CoachingPlan(Base):
    __tablename__ = "coaching_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    skill_assessment: Mapped[Optional[str]] = mapped_column(Text)
    identified_weaknesses: Mapped[Optional[dict]] = mapped_column(JSONB)
    retrieved_chunk_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    seven_day_plan: Mapped[Optional[dict]] = mapped_column(JSONB)
    loadout_recommendations: Mapped[Optional[dict]] = mapped_column(JSONB)
    rank_roadmap: Mapped[Optional[str]] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ProgressLog(Base):
    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("coaching_plans.id"), nullable=False)
    stats_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    improvement_delta: Mapped[Optional[dict]] = mapped_column(JSONB)
    agent_feedback: Mapped[Optional[str]] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating IN (-1, 1)", name="feedback_rating_check"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("coaching_plans.id"), nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
