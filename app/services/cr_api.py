"""Clash Royale official API client."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

CR_API_BASE = "https://api.clashroyale.com/v1"


class CrApiError(Exception):
    """Base error for Clash Royale API failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_player_tag(tag: str) -> str:
    """Ensure tag is uppercase and starts with # (CR format)."""
    cleaned = tag.strip().upper().replace("%23", "#")
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    return cleaned


def _api_key() -> str:
    load_dotenv()
    key = os.getenv("CR_API_KEY")
    if not key or key == "your_key_here":
        raise CrApiError("CR_API_KEY is missing or unset in .env", status_code=503)
    return key


def _win_rate(wins: int | None, losses: int | None) -> float | None:
    """Compute win % from lifetime wins/losses when both are present."""
    if wins is None or losses is None:
        return None
    total = wins + losses
    if total <= 0:
        return None
    return round((wins / total) * 100.0, 2)


def _map_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Map CR JSON into the slim dict our assembler will consume."""
    arena = raw.get("arena") or {}
    favourite = raw.get("currentFavouriteCard") or {}
    deck = [
        {
            "name": card.get("name"),
            "level": card.get("level"),
            "max_level": card.get("maxLevel"),
            "elixir_cost": card.get("elixirCost"),
        }
        for card in raw.get("currentDeck") or []
    ]
    return {
        "tag": raw.get("tag"),
        "name": raw.get("name"),
        "trophies": raw.get("trophies"),
        "best_trophies": raw.get("bestTrophies"),
        "exp_level": raw.get("expLevel"),
        "arena": {
            "id": arena.get("id"),
            "name": arena.get("name"),
        },
        "wins": raw.get("wins"),
        "losses": raw.get("losses"),
        "win_rate": _win_rate(raw.get("wins"), raw.get("losses")),
        "favourite_card": favourite.get("name"),
        "current_deck": deck,
        "source": "live_api",
    }


async def get_player(tag: str) -> dict[str, Any]:
    """
    Fetch a player from the Clash Royale API.

    Calls GET /v1/players/{tag}. Returns trophies, arena, win_rate,
    favourite_card, current_deck (+ tag/name for context).
    """
    player_tag = normalize_player_tag(tag)
    encoded_tag = quote(player_tag, safe="")
    url = f"{CR_API_BASE}/players/{encoded_tag}"
    headers = {"Authorization": f"Bearer {_api_key()}", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.exception("CR API request failed for tag=%s", player_tag)
        raise CrApiError(f"CR API request failed: {exc}", status_code=503) from exc

    if response.status_code == 404:
        raise CrApiError(f"CR player not found: {player_tag}", status_code=404)
    if response.status_code == 403:
        raise CrApiError(
            "CR API rejected the key (check CR_API_KEY and IP allowlist)",
            status_code=403,
        )
    if response.status_code >= 400:
        logger.error(
            "CR API error status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
        raise CrApiError(
            f"CR API error ({response.status_code})",
            status_code=502,
        )

    mapped = _map_player(response.json())
    logger.info(
        "Fetched CR player tag=%s trophies=%s arena=%s",
        mapped.get("tag"),
        mapped.get("trophies"),
        (mapped.get("arena") or {}).get("name"),
    )
    return mapped
