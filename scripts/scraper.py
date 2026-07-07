"""Scrape Fandom wiki strategy articles into markdown with YAML frontmatter."""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
import yaml
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "games"
REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Tags to strip from Fandom article body before extraction
NOISE_SELECTORS = [
    "table.infobox",
    "div.infobox",
    "div.navbox",
    "table.navbox",
    "aside",
    "script",
    "style",
    "div.mw-editsection",
    "div.toc",
    "ol.references",
    "div.reflist",
    "div.catlinks",
    "div.wikia-gallery",
    "figure",
    "sup.reference",
]

# Elements that carry article content
CONTENT_SELECTORS = ["div.mw-parser-output", "div#mw-content-text"]


@dataclass(frozen=True)
class ArticleSpec:
    url: str
    slug: str
    topic: str
    weakness_category: str
    skill_level: str
    mode: str
    experience_level: str
    weapon_class: str = "any"


@dataclass(frozen=True)
class GameScrapeConfig:
    game: str
    genre: str
    articles: list[ArticleSpec]


SCRAPE_TARGETS: list[GameScrapeConfig] = [
    GameScrapeConfig(
        game="gta_v_online",
        genre="open_world",
        articles=[
            ArticleSpec(
                url="https://gta.fandom.com/wiki/GTA_Online",
                slug="gta_online_overview",
                topic="online_basics",
                weakness_category="progression",
                skill_level="beginner",
                mode="online",
                experience_level="new",
            ),
            ArticleSpec(
                url="https://gta.fandom.com/wiki/Heists",
                slug="heists_guide",
                topic="heists",
                weakness_category="mission_strategy",
                skill_level="intermediate",
                mode="online",
                experience_level="intermediate",
            ),
            ArticleSpec(
                url="https://gta.fandom.com/wiki/Weapons_in_GTA_V",
                slug="weapons_guide",
                topic="weapons",
                weakness_category="combat",
                skill_level="intermediate",
                mode="online",
                experience_level="intermediate",
                weapon_class="any",
            ),
            ArticleSpec(
                url="https://gta.fandom.com/wiki/Missions_in_GTA_Online",
                slug="online_missions",
                topic="missions",
                weakness_category="mission_strategy",
                skill_level="beginner",
                mode="online",
                experience_level="new",
            ),
            ArticleSpec(
                url="https://gta.fandom.com/wiki/Motorcycle_Club",
                slug="mc_business_guide",
                topic="mc_business",
                weakness_category="money_making",
                skill_level="intermediate",
                mode="online",
                experience_level="intermediate",
            ),
        ],
    ),
    GameScrapeConfig(
        game="cod",
        genre="shooter",
        articles=[
            ArticleSpec(
                url="https://callofduty.fandom.com/wiki/Call_of_Duty:_Warzone",
                slug="warzone_overview",
                topic="warzone_basics",
                weakness_category="game_sense",
                skill_level="beginner",
                mode="warzone",
                experience_level="new",
            ),
            ArticleSpec(
                url="https://callofduty.fandom.com/wiki/Create-A-Class",
                slug="create_a_class",
                topic="loadouts",
                weakness_category="loadout",
                skill_level="intermediate",
                mode="multiplayer",
                experience_level="intermediate",
                weapon_class="any",
            ),
            ArticleSpec(
                url="https://callofduty.fandom.com/wiki/Perks",
                slug="perks_guide",
                topic="perks",
                weakness_category="loadout",
                skill_level="intermediate",
                mode="multiplayer",
                experience_level="intermediate",
            ),
            ArticleSpec(
                url="https://callofduty.fandom.com/wiki/Killstreak",
                slug="killstreaks_guide",
                topic="killstreaks",
                weakness_category="game_sense",
                skill_level="intermediate",
                mode="multiplayer",
                experience_level="intermediate",
            ),
            ArticleSpec(
                url="https://callofduty.fandom.com/wiki/Attachments",
                slug="attachments_guide",
                topic="attachments",
                weakness_category="loadout",
                skill_level="beginner",
                mode="multiplayer",
                experience_level="new",
                weapon_class="any",
            ),
        ],
    ),
]


def _page_name_from_url(url: str) -> str:
    """Extract MediaWiki page title from a Fandom URL (keep underscores)."""
    return unquote(url.rstrip("/").split("/wiki/")[-1])


def fetch_page(url: str) -> str:
    """Download article HTML via the Fandom MediaWiki API."""
    wiki_base = url.split("/wiki/")[0]
    page_name = _page_name_from_url(url)
    api_url = f"{wiki_base}/api.php"
    response = requests.get(
        api_url,
        params={
            "action": "parse",
            "page": page_name,
            "format": "json",
            "prop": "text",
            "disableeditsection": "true",
        },
        headers=DEFAULT_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise ValueError(payload["error"].get("info", "MediaWiki API error"))
    return payload["parse"]["text"]["*"]


def _find_content_root(soup: BeautifulSoup) -> Tag:
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node:
            return node
    # MediaWiki API returns an HTML fragment without outer wrappers
    if soup.body:
        return soup.body
    return soup


def _strip_noise(root: Tag) -> None:
    for selector in NOISE_SELECTORS:
        for node in root.select(selector):
            node.decompose()


def _heading_level(tag_name: str) -> int:
    if tag_name.startswith("h") and tag_name[1:].isdigit():
        return int(tag_name[1:])
    return 2


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tag_to_markdown(tag: Tag) -> str:
    if tag.name in {"h2", "h3", "h4"}:
        level = _heading_level(tag.name)
        title = _clean_text(tag.get_text(" ", strip=True))
        if not title:
            return ""
        prefix = "#" * min(level + 1, 6)
        return f"{prefix} {title}"

    if tag.name == "p":
        text = _clean_text(tag.get_text(" ", strip=True))
        return text

    if tag.name in {"ul", "ol"}:
        lines: list[str] = []
        for item in tag.find_all("li", recursive=False):
            item_text = _clean_text(item.get_text(" ", strip=True))
            if item_text:
                lines.append(f"- {item_text}")
        return "\n".join(lines)

    return ""


def extract_markdown_body(html: str, fallback_title: str) -> tuple[str, str]:
    """Return (title, markdown_body) from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1.page-header__title, h1#firstHeading, h1")
    title = _clean_text(title_node.get_text()) if title_node else fallback_title
    root = _find_content_root(soup)
    _strip_noise(root)

    blocks: list[str] = []
    for child in root.find_all(["h2", "h3", "h4", "p", "ul", "ol"]):
        block = _tag_to_markdown(child)
        if block:
            blocks.append(block)

    body = "\n\n".join(blocks).strip()
    if not body:
        raise ValueError("No usable article text after cleanup")

    return title, body


def build_frontmatter(game_cfg: GameScrapeConfig, article: ArticleSpec) -> dict[str, Any]:
    return {
        "game": game_cfg.game,
        "genre": game_cfg.genre,
        "mode": article.mode,
        "topic": article.topic,
        "weakness_category": article.weakness_category,
        "skill_level": article.skill_level,
        "weapon_class": article.weapon_class,
        "experience_level": article.experience_level,
        "source": "fandom_wiki",
        "last_updated": "2026-07",
    }


def write_markdown(
    game_cfg: GameScrapeConfig,
    article: ArticleSpec,
    title: str,
    body: str,
) -> Path:
    output_dir = DATA_DIR / game_cfg.game
    output_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = build_frontmatter(game_cfg, article)
    yaml_block = yaml.safe_dump(frontmatter, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n# {title}\n\n{body}\n"

    output_path = output_dir / f"{article.slug}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def scrape_article(game_cfg: GameScrapeConfig, article: ArticleSpec) -> Path | None:
    """Scrape one article and save it as markdown. Returns path or None on failure."""
    logger.info("Scraping %s — %s", game_cfg.game, article.url)
    try:
        html = fetch_page(article.url)
        title, body = extract_markdown_body(html, fallback_title=article.slug.replace("_", " ").title())
        output_path = write_markdown(game_cfg, article, title, body)
        logger.info("Saved %s", output_path.relative_to(DATA_DIR.parent.parent))
        return output_path
    except Exception:
        logger.exception("Failed to scrape %s", article.url)
        return None


def scrape_games(game_names: list[str] | None = None) -> dict[str, int]:
    """Scrape configured games. Returns {game: saved_count}."""
    targets = SCRAPE_TARGETS
    if game_names:
        targets = [cfg for cfg in SCRAPE_TARGETS if cfg.game in game_names]

    results: dict[str, int] = {}
    for game_cfg in targets:
        saved = 0
        for article in game_cfg.articles:
            if scrape_article(game_cfg, article):
                saved += 1
            time.sleep(REQUEST_DELAY_SECONDS)
        results[game_cfg.game] = saved
        logger.info("Finished %s — saved %d/%d", game_cfg.game, saved, len(game_cfg.articles))

    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scrape_games(["gta_v_online", "cod"])


if __name__ == "__main__":
    main()
