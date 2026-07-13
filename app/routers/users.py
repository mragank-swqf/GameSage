"""Users + per-game profile endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Game, User, UserProfile
from app.db.session import get_db
from app.schemas.user_schemas import (
    UserCreate,
    UserProfileCreate,
    UserProfileResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Users"])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    description="Create a GameSage user (username + email). No auth — demo identity only.",
    response_description="The created user with assigned id.",
)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = User(username=body.username, email=str(body.email))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("Duplicate user create attempt: %s", body.username)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        ) from None

    await db.refresh(user)
    logger.info("Created user id=%s username=%s", user.id, user.username)
    return user


@router.post(
    "/users/{user_id}/profile",
    response_model=UserProfileResponse,
    description=(
        "Create or update a per-game profile "
        "(experience_level, preferred_playstyle, notes)."
    ),
    response_description="The upserted user profile row.",
)
async def upsert_user_profile(
    user_id: int,
    body: UserProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    game = await db.get(Game, body.game_id)
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game {body.game_id} not found",
        )

    result = await db.execute(
        select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.game_id == body.game_id,
        )
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(
            user_id=user_id,
            game_id=body.game_id,
            experience_level=body.experience_level,
            preferred_playstyle=body.preferred_playstyle,
            notes=body.notes,
        )
        db.add(profile)
        logger.info(
            "Created profile user_id=%s game_id=%s", user_id, body.game_id
        )
    else:
        profile.experience_level = body.experience_level
        profile.preferred_playstyle = body.preferred_playstyle
        profile.notes = body.notes
        logger.info(
            "Updated profile user_id=%s game_id=%s", user_id, body.game_id
        )

    await db.commit()
    await db.refresh(profile)
    return profile


@router.get(
    "/users/{user_id}/profile/{game_id}",
    response_model=UserProfileResponse,
    description="Fetch a user's profile for one game.",
    response_description="The stored per-game profile.",
)
async def get_user_profile(
    user_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    result = await db.execute(
        select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.game_id == game_id,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No profile for user {user_id} and game {game_id}",
        )
    return profile
