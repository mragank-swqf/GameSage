"""Semantic chunker — split strategy markdown into RAG-ready chunks.

Rules:
- Split on ## / ### headers (semantic boundaries)
- Target 300–500 tokens per chunk; ~50 token overlap only when a section must be split
- Never split a short strategy unit (loadout / deck / layout block) across chunks
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "games"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "chunks.jsonl"

MIN_TOKENS = 300
MAX_TOKENS = 500
OVERLAP_TOKENS = 50

# Approximate tokens without a tokenizer dependency (portfolio-friendly)
CHARS_PER_TOKEN = 4

HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    content: str
    game: str
    genre: str
    mode: str
    topic: str
    weakness_category: str
    skill_level: str
    weapon_class: str
    experience_level: str
    source: str
    heading: str
    token_estimate: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def parse_markdown_file(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter, body_without_frontmatter)."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"Missing YAML frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return frontmatter, body


def split_into_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown body into (heading, section_text) pairs.

    Content before the first ##/### is kept under the H1 title (or 'intro').
    """
    matches = list(HEADER_RE.finditer(body))
    if not matches:
        title_match = re.match(r"^#\s+(.+)$", body, re.MULTILINE)
        heading = title_match.group(1).strip() if title_match else "intro"
        return [(heading, body)]

    sections: list[tuple[str, str]] = []
    # Preface before first ##/###
    preface = body[: matches[0].start()].strip()
    if preface:
        title_match = re.match(r"^#\s+(.+)$", preface, re.MULTILINE)
        heading = title_match.group(1).strip() if title_match else "intro"
        sections.append((heading, preface))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        if section_text:
            sections.append((heading, section_text))

    return sections


def _hard_split(text: str, max_tokens: int = MAX_TOKENS) -> list[str]:
    """Character-window split when paragraph boundaries are not enough."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return parts


def split_long_section(text: str, max_tokens: int = MAX_TOKENS) -> list[str]:
    """Split an oversized section on paragraph boundaries with token overlap."""
    if estimate_tokens(text) <= max_tokens:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        return _hard_split(text, max_tokens)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        # Single paragraph larger than the budget — hard-split it alone
        if para_tokens > max_tokens:
            if current:
                chunks.append("\n\n".join(current))
                current, current_tokens = [], 0
            chunks.extend(_hard_split(para, max_tokens))
            continue

        if current and current_tokens + para_tokens > max_tokens:
            chunks.append("\n\n".join(current))
            overlap: list[str] = []
            overlap_tokens = 0
            for prev in reversed(current):
                t = estimate_tokens(prev)
                if overlap_tokens + t > OVERLAP_TOKENS:
                    break
                overlap.insert(0, prev)
                overlap_tokens += t
            current = overlap + [para]
            current_tokens = sum(estimate_tokens(p) for p in current)
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def merge_small_sections(
    sections: list[tuple[str, str]],
    min_tokens: int = MIN_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> list[tuple[str, str]]:
    """Merge consecutive tiny sections so chunks are not sparse stubs."""
    if not sections:
        return []

    merged: list[tuple[str, str]] = []
    buf_heading, buf_text = sections[0]
    buf_tokens = estimate_tokens(buf_text)

    for heading, text in sections[1:]:
        text_tokens = estimate_tokens(text)
        # Keep strategy units intact: if current buffer is already a solid chunk
        # and next section is also substantial, do not glue loadouts together.
        if buf_tokens >= min_tokens and text_tokens >= min_tokens // 2:
            merged.append((buf_heading, buf_text))
            buf_heading, buf_text = heading, text
            buf_tokens = text_tokens
            continue

        combined_tokens = buf_tokens + text_tokens
        if combined_tokens <= max_tokens and buf_tokens < min_tokens:
            buf_text = f"{buf_text}\n\n{text}"
            buf_heading = f"{buf_heading} | {heading}"
            buf_tokens = combined_tokens
        else:
            merged.append((buf_heading, buf_text))
            buf_heading, buf_text = heading, text
            buf_tokens = text_tokens

    merged.append((buf_heading, buf_text))
    return merged


def chunk_file(path: Path) -> list[Chunk]:
    frontmatter, body = parse_markdown_file(path)
    game = str(frontmatter.get("game", path.parent.name))
    slug = path.stem

    sections = split_into_sections(body)
    sections = merge_small_sections(sections)

    chunks: list[Chunk] = []
    part = 0
    for heading, section_text in sections:
        pieces = split_long_section(section_text)
        for piece in pieces:
            part += 1
            chunk_id = f"{game}_{slug}_{part:03d}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    content=piece,
                    game=game,
                    genre=str(frontmatter.get("genre", "")),
                    mode=str(frontmatter.get("mode", "")),
                    topic=str(frontmatter.get("topic", "")),
                    weakness_category=str(frontmatter.get("weakness_category", "")),
                    skill_level=str(frontmatter.get("skill_level", "")),
                    weapon_class=str(frontmatter.get("weapon_class", "any")),
                    experience_level=str(frontmatter.get("experience_level", "")),
                    source=str(frontmatter.get("source", "fandom_wiki")),
                    heading=heading,
                    token_estimate=estimate_tokens(piece),
                )
            )
    return chunks


def chunk_corpus(game_names: list[str] | None = None) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    game_dirs = sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    if game_names:
        game_dirs = [p for p in game_dirs if p.name in game_names]

    for game_dir in game_dirs:
        md_files = sorted(game_dir.glob("*.md"))
        for path in md_files:
            try:
                file_chunks = chunk_file(path)
                all_chunks.extend(file_chunks)
                logger.info(
                    "%s — %d chunk(s)",
                    path.relative_to(DATA_DIR.parent.parent),
                    len(file_chunks),
                )
            except Exception:
                logger.exception("Failed to chunk %s", path)

    return all_chunks


def write_chunks(chunks: list[Chunk], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
    logger.info("Wrote %d chunks → %s", len(chunks), output_path)


def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO)
    game_names = sys.argv[1:] or None
    chunks = chunk_corpus(game_names)
    write_chunks(chunks)

    by_game: dict[str, int] = {}
    for c in chunks:
        by_game[c.game] = by_game.get(c.game, 0) + 1
    for game, count in sorted(by_game.items()):
        logger.info("  %s: %d chunks", game, count)
    logger.info(
        "Token range — min: %d, max: %d, avg: %d",
        min((c.token_estimate for c in chunks), default=0),
        max((c.token_estimate for c in chunks), default=0),
        (sum(c.token_estimate for c in chunks) // len(chunks)) if chunks else 0,
    )


if __name__ == "__main__":
    main()
