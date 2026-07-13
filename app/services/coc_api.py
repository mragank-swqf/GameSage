"""Clash of Clans official API client."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

COC_API_BASE = "https://api.clashofclans.com/v1"


class CocApiError(Exception):
    """Base error for CoC API failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_player_tag(tag: str) -> str:
    """Ensure tag is uppercase and starts with # (CoC format)."""
    cleaned = tag.strip().upper().replace("%23", "#")
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    return cleaned


def _api_key() -> str:
    load_dotenv()
    key = os.getenv("COC_API_KEY")
    if not key or key == "your_key_here":
        raise CocApiError("COC_API_KEY is missing or unset in .env", status_code=503)
    return key


def _map_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Map CoC JSON into the slim dict our assembler will consume."""
    heroes = [
        {
            "name": hero.get("name"),
            "level": hero.get("level"),
            "max_level": hero.get("maxLevel"),
            "village": hero.get("village"),
        }
        for hero in raw.get("heroes") or []
    ]
    return {
        "tag": raw.get("tag"),
        "name": raw.get("name"),
        "town_hall_level": raw.get("townHallLevel"),
        "trophies": raw.get("trophies"),
        "war_stars": raw.get("warStars"),
        "exp_level": raw.get("expLevel"),
        "heroes": heroes,
        "source": "live_api",
    }


async def get_player(tag: str) -> dict[str, Any]:
    """
    Fetch a player from the CoC API.

    Calls GET /v1/players/{tag}. Returns town_hall_level, trophies,
    war_stars, heroes (+ tag/name for context).
    """
    player_tag = normalize_player_tag(tag)
    encoded_tag = quote(player_tag, safe="")
    url = f"{COC_API_BASE}/players/{encoded_tag}"
    headers = {"Authorization": f"Bearer {_api_key()}", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.exception("CoC API request failed for tag=%s", player_tag)
        raise CocApiError(f"CoC API request failed: {exc}", status_code=503) from exc

    if response.status_code == 404:
        raise CocApiError(f"CoC player not found: {player_tag}", status_code=404)
    if response.status_code == 403:
        raise CocApiError(
            "CoC API rejected the key (check COC_API_KEY and IP allowlist)",
            status_code=403,
        )
    if response.status_code >= 400:
        logger.error(
            "CoC API error status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
        raise CocApiError(
            f"CoC API error ({response.status_code})",
            status_code=502,
        )

    mapped = _map_player(response.json())
    logger.info(
        "Fetched CoC player tag=%s th=%s trophies=%s",
        mapped.get("tag"),
        mapped.get("town_hall_level"),
        mapped.get("trophies"),
    )
    return mapped
