"""Canonical weakness taxonomy and topic → weakness_category mapping.

Import from here — never hardcode weakness labels elsewhere.
"""

from __future__ import annotations

# Genre → allowed weakness labels (Step 2 assessor + Step 3 Qdrant filters)
WEAKNESS_CATEGORIES: dict[str, list[str]] = {
    "shooter": [
        "positioning",
        "aim",
        "game_sense",
        "loadout",
        "movement",
        "team_comms",
    ],
    "strategy": [
        "deck_building",
        "resource_management",
        "base_layout",
        "troop_deployment",
        "timing",
    ],
    "open_world": [
        "mission_strategy",
        "money_making",
        "combat",
        "stealth",
        "progression",
    ],
}

# Game name → genre (matches seed.py / scraper)
GAME_GENRE: dict[str, str] = {
    "cod": "shooter",
    "free_fire": "shooter",
    "coc": "strategy",
    "cr": "strategy",
    "gta_v_online": "open_world",
    "rdr2": "open_world",
}

# Document topic (YAML frontmatter) → weakness_category
# Default map; genre-specific overrides below for shared topic names (e.g. "weapons")
TOPIC_TO_WEAKNESS: dict[str, str] = {
    # Shooter
    "attachments": "loadout",
    "loadouts": "loadout",
    "perks": "loadout",
    "characters": "loadout",
    "killstreaks": "game_sense",
    "warzone_basics": "game_sense",
    "basics": "game_sense",
    "maps": "positioning",
    "ranked": "positioning",
    # Strategy
    "decks": "deck_building",
    "cards": "deck_building",
    "elixir": "timing",
    "trophies": "timing",
    "arenas": "resource_management",
    "town_hall": "resource_management",
    "base_layout": "base_layout",
    "attacking": "troop_deployment",
    "heroes": "troop_deployment",
    "clan_wars": "timing",
    # Open world
    "heists": "mission_strategy",
    "missions": "mission_strategy",
    "honor": "mission_strategy",
    "online_basics": "progression",
    "money": "money_making",
    "money_making": "money_making",
    "hunting": "money_making",
    "mc_business": "money_making",
}

# Same topic name, different genre → different weakness
TOPIC_TO_WEAKNESS_BY_GENRE: dict[str, dict[str, str]] = {
    "weapons": {
        "shooter": "loadout",
        "open_world": "combat",
    },
}


def get_weaknesses_for_genre(genre: str) -> list[str]:
    """Return allowed weakness labels for a genre."""
    return list(WEAKNESS_CATEGORIES.get(genre, []))


def get_weaknesses_for_game(game: str) -> list[str]:
    """Return allowed weakness labels for a game name."""
    genre = GAME_GENRE.get(game, "")
    return get_weaknesses_for_genre(genre)


def map_topic_to_weakness(topic: str, game: str = "") -> str | None:
    """Map a document topic to a taxonomy weakness_category. None if unmapped."""
    key = topic.strip().lower()
    genre = GAME_GENRE.get(game, "")

    if key in TOPIC_TO_WEAKNESS_BY_GENRE:
        by_genre = TOPIC_TO_WEAKNESS_BY_GENRE[key]
        if genre in by_genre:
            return by_genre[genre]
        # Fall through to default if genre not listed

    return TOPIC_TO_WEAKNESS.get(key)


def is_valid_weakness(game: str, weakness: str) -> bool:
    """True if weakness is in the allowed taxonomy for this game."""
    return weakness in get_weaknesses_for_game(game)
