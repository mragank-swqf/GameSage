"""initial schema — all 7 tables

Revision ID: 8a3f1c2d9e01
Revises:
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8a3f1c2d9e01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=False),
        sa.Column("supported_modes", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("has_live_api", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("experience_level", sa.String(length=20), nullable=True),
        sa.Column("preferred_playstyle", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "game_id"),
    )

    op.create_table(
        "player_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("current_rank", sa.String(length=50), nullable=True),
        sa.Column("kd_ratio", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("win_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("weekly_playtime_hours", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("preferred_weapons", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("known_weaknesses", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("goals", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="user_submitted",
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "coaching_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("skill_assessment", sa.Text(), nullable=True),
        sa.Column("identified_weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retrieved_chunk_ids", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("seven_day_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("loadout_recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rank_roadmap", sa.Text(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "progress_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("stats_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("improvement_delta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_feedback", sa.Text(), nullable=True),
        sa.Column(
            "logged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["coaching_plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating IN (-1, 1)", name="feedback_rating_check"),
        sa.ForeignKeyConstraint(["plan_id"], ["coaching_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("progress_logs")
    op.drop_table("coaching_plans")
    op.drop_table("player_stats")
    op.drop_table("user_profiles")
    op.drop_table("games")
    op.drop_table("users")
