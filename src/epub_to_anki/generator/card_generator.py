"""Generate flashcards from chapter content using Claude."""

import json
import re
import uuid
from typing import Callable, Optional

import anthropic

from ..models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    Density,
)
from .prompts import GENERATION_PROMPT_TEMPLATE, SYSTEM_PROMPT


def generate_card_id() -> str:
    """Generate a unique card ID."""
    return str(uuid.uuid4())[:8]


def chunk_content(content: str, max_tokens: int = 12000) -> list[str]:
    """
    Split content into chunks that fit within token limits.

    Uses a rough estimate of ~4 chars per token.
    """
    max_chars = max_tokens * 4
    if len(content) <= max_chars:
        return [content]

    # Split by paragraphs
    paragraphs = content.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for para in paragraphs:
        para_length = len(para) + 2  # +2 for \n\n
        if current_length + para_length > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_length = para_length
        else:
            current_chunk.append(para)
            current_length += para_length

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def parse_cards_from_response(
    response_text: str,
    chapter: Chapter,
) -> list[Card]:
    """Parse Claude's JSON response into Card objects."""
    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON array
        json_match = re.search(r"\[[\s\S]*\]", response_text)
        if json_match:
            json_str = json_match.group(0)
        else:
            return []

    try:
        raw_cards = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    cards: list[Card] = []
    for raw in raw_cards:
        try:
            card_format = CardFormat(raw.get("format", "qa"))
            card_type = CardType(raw.get("card_type", "concept"))

            card = Card(
                id=generate_card_id(),
                format=card_format,
                card_type=card_type,
                question=raw.get("question"),
                answer=raw.get("answer"),
                cloze_text=raw.get("cloze_text"),
                importance=max(1, min(10, int(raw.get("importance", 5)))),
                difficulty=max(1, min(10, int(raw.get("difficulty", 5)))),
                source_chapter=chapter.title,
                source_chapter_index=chapter.index,
                source_section=raw.get("source_section"),
                source_quote=raw.get("source_quote"),
                status=CardStatus.INCLUDED,
                tags=[
                    f"chapter::{chapter.index + 1:02d}_{slugify(chapter.title)}",
                    f"type::{card_type.value}",
                    f"format::{card_format.value}",
                ],
            )

            # Validate card has required content
            if card_format == CardFormat.QA:
                if not card.question or not card.answer:
                    continue
            else:
                if not card.cloze_text:
                    continue

            cards.append(card)
        except (ValueError, KeyError):
            continue

    return cards


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text[:30].strip("_")


class CardGenerator:
    """Generate flashcards from book chapters using Claude."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """
        Initialize the card generator.

        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            model: Claude model to use
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_for_chapter(
        self,
        book: Book,
        chapter: Chapter,
        density: Density = Density.MEDIUM,
    ) -> ChapterCards:
        """
        Generate flashcards for a single chapter.

        Args:
            book: The book metadata
            chapter: The chapter to process
            density: Card generation density

        Returns:
            ChapterCards with all generated cards
        """
        all_cards: list[Card] = []

        # Chunk content if needed
        chunks = chunk_content(chapter.content)

        for chunk_idx, chunk in enumerate(chunks):
            prompt = GENERATION_PROMPT_TEMPLATE.format(
                book_title=book.title,
                book_author=book.author,
                chapter_num=chapter.index + 1,
                chapter_title=chapter.title,
                density=density.value,
                chapter_content=chunk,
            )

            # Add context if multiple chunks
            if len(chunks) > 1:
                prompt = f"[Part {chunk_idx + 1} of {len(chunks)}]\n\n" + prompt

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            # Safely extract response text
            if not response.content or len(response.content) == 0:
                continue
            content_block = response.content[0]
            if not hasattr(content_block, "text"):
                continue
            response_text = content_block.text

            cards = parse_cards_from_response(response_text, chapter)
            all_cards.extend(cards)

        return ChapterCards(
            chapter=chapter,
            cards=all_cards,
            density_used=density,
        )

    def generate_for_book(
        self,
        book: Book,
        density: Density = Density.MEDIUM,
        chapter_indices: Optional[list[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[ChapterCards]:
        """
        Generate flashcards for multiple chapters.

        Args:
            book: The book to process
            density: Card generation density
            chapter_indices: Specific chapters to process (None = all)
            progress_callback: Optional callback(chapter_idx, total, chapter_title)

        Returns:
            List of ChapterCards for each processed chapter
        """
        chapters_to_process = book.chapters
        if chapter_indices:
            chapters_to_process = [
                ch for ch in book.chapters if ch.index in chapter_indices
            ]

        results: list[ChapterCards] = []
        total = len(chapters_to_process)

        for idx, chapter in enumerate(chapters_to_process):
            if progress_callback:
                progress_callback(idx, total, chapter.title)

            chapter_cards = self.generate_for_chapter(book, chapter, density)
            results.append(chapter_cards)

        return results
