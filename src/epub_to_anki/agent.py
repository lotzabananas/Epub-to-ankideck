"""
Claude Code SDK Agent for EPUB to Anki conversion.

This module provides an agent interface that can be used with Claude Code
for interactive book-to-flashcard conversion.
"""

import json
from pathlib import Path
from typing import Optional

from .exporter import AnkiExporter
from .exporter.anki_exporter import export_cards_to_json
from .generator import CardGenerator
from .models import Book, CardStatus, ChapterCards, Density
from .parser import parse_epub
from .parser.epub_parser import get_book_summary
from .ranker import CardRanker


class EpubToAnkiAgent:
    """
    Agent for converting EPUB books to Anki flashcards.

    This agent maintains state across interactions, allowing for:
    - Loading and inspecting books
    - Generating cards chapter by chapter
    - Adjusting thresholds interactively
    - Exporting to Anki format

    Designed to work with Claude Code SDK for rich interactive sessions.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.generator = CardGenerator(api_key=api_key)
        self.ranker = CardRanker()

        # Session state
        self.book: Optional[Book] = None
        self.chapter_cards: dict[int, ChapterCards] = {}
        self.output_dir: Optional[Path] = None
        self.density = Density.MEDIUM

    def load_book(self, epub_path: str) -> dict:
        """
        Load an EPUB file and return book information.

        Args:
            epub_path: Path to the EPUB file

        Returns:
            Dict with book metadata and chapter list
        """
        self.book = parse_epub(epub_path)
        self.chapter_cards = {}

        # Set default output directory
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in self.book.title
        )
        self.output_dir = Path("output") / safe_title

        return {
            "title": self.book.title,
            "author": self.book.author,
            "total_chapters": len(self.book.chapters),
            "total_words": self.book.total_words,
            "chapters": [
                {
                    "index": ch.index,
                    "title": ch.title,
                    "word_count": ch.word_count,
                }
                for ch in self.book.chapters
            ],
        }

    def set_density(self, density: str) -> dict:
        """
        Set the card generation density.

        Args:
            density: One of 'light', 'medium', 'thorough'

        Returns:
            Confirmation with expected cards per page
        """
        self.density = Density(density)

        descriptions = {
            Density.LIGHT: "~1 card per 2-3 pages (core concepts only)",
            Density.MEDIUM: "~1 card per page (key ideas + facts)",
            Density.THOROUGH: "~2-3 cards per page (comprehensive)",
        }

        return {
            "density": density,
            "description": descriptions[self.density],
        }

    def generate_chapter(self, chapter_index: int) -> dict:
        """
        Generate flashcards for a specific chapter.

        Args:
            chapter_index: 0-indexed chapter number

        Returns:
            Summary of generated cards with score distribution
        """
        if not self.book:
            raise ValueError("No book loaded. Call load_book first.")

        chapter = self.book.chapters[chapter_index]
        chapter_cards = self.generator.generate_for_chapter(
            self.book, chapter, self.density
        )

        # Rank cards
        self.ranker.rank_chapter(chapter_cards)

        # Store in session
        self.chapter_cards[chapter_index] = chapter_cards

        # Get statistics
        stats = self.ranker.get_score_distribution(chapter_cards)

        return {
            "chapter_index": chapter_index,
            "chapter_title": chapter.title,
            "total_cards": len(chapter_cards.cards),
            "score_distribution": stats,
            "sample_cards": [
                {
                    "format": c.format.value,
                    "type": c.card_type.value,
                    "content": c.get_display_text(),
                    "importance": c.importance,
                    "difficulty": c.difficulty,
                    "score": round(c.compute_score(), 1),
                }
                for c in chapter_cards.cards[:5]
            ],
        }

    def preview_threshold(self, chapter_index: int, threshold: float) -> dict:
        """
        Preview what a threshold would do for a chapter.

        Args:
            chapter_index: Chapter to preview
            threshold: Score threshold (1-10)

        Returns:
            Counts of what would be included/excluded
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        chapter_cards = self.chapter_cards[chapter_index]
        return self.ranker.preview_threshold(chapter_cards, threshold)

    def apply_threshold(self, chapter_index: int, threshold: float) -> dict:
        """
        Apply a threshold to filter cards for a chapter.

        Args:
            chapter_index: Chapter to filter
            threshold: Score threshold (1-10)

        Returns:
            Summary of included/excluded cards
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        chapter_cards = self.chapter_cards[chapter_index]
        self.ranker.apply_custom_threshold(chapter_cards, threshold)

        return {
            "chapter_index": chapter_index,
            "threshold_applied": threshold,
            "included": len(chapter_cards.included_cards),
            "excluded": len(chapter_cards.excluded_cards),
        }

    def apply_auto_threshold(self, chapter_index: int) -> dict:
        """
        Apply density-based automatic threshold to a chapter.

        Args:
            chapter_index: Chapter to filter

        Returns:
            Summary of filtering result
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        chapter_cards = self.chapter_cards[chapter_index]
        self.ranker.apply_density_threshold(chapter_cards, self.density)

        return {
            "chapter_index": chapter_index,
            "density": self.density.value,
            "threshold_applied": chapter_cards.threshold,
            "included": len(chapter_cards.included_cards),
            "excluded": len(chapter_cards.excluded_cards),
        }

    def get_cards(
        self,
        chapter_index: int,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """
        Get cards from a chapter with optional filtering.

        Args:
            chapter_index: Chapter to get cards from
            status: Filter by 'included' or 'excluded' (None for all)
            limit: Maximum cards to return
            offset: Starting offset for pagination

        Returns:
            List of cards with metadata
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        chapter_cards = self.chapter_cards[chapter_index]

        if status == "included":
            cards = chapter_cards.included_cards
        elif status == "excluded":
            cards = chapter_cards.excluded_cards
        else:
            cards = chapter_cards.cards

        total = len(cards)
        cards = cards[offset : offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "cards": [
                {
                    "id": c.id,
                    "format": c.format.value,
                    "type": c.card_type.value,
                    "content": c.get_display_text(),
                    "importance": c.importance,
                    "difficulty": c.difficulty,
                    "score": round(c.compute_score(), 1),
                    "status": c.status.value,
                    "source_section": c.source_section,
                }
                for c in cards
            ],
        }

    def toggle_card(self, chapter_index: int, card_id: str) -> dict:
        """
        Toggle a card's included/excluded status.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card to toggle

        Returns:
            Updated card status
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                if card.status == CardStatus.INCLUDED:
                    card.status = CardStatus.EXCLUDED
                else:
                    card.status = CardStatus.INCLUDED

                return {
                    "card_id": card_id,
                    "new_status": card.status.value,
                }

        raise ValueError(f"Card {card_id} not found")

    def get_summary(self) -> dict:
        """
        Get summary of all processed chapters.

        Returns:
            Overall statistics and per-chapter breakdown
        """
        if not self.book:
            raise ValueError("No book loaded.")

        chapters_summary = []
        total_included = 0
        total_excluded = 0

        for idx, chapter in enumerate(self.book.chapters):
            if idx in self.chapter_cards:
                cc = self.chapter_cards[idx]
                included = len(cc.included_cards)
                excluded = len(cc.excluded_cards)
                total_included += included
                total_excluded += excluded

                chapters_summary.append(
                    {
                        "index": idx,
                        "title": chapter.title,
                        "status": "processed",
                        "included": included,
                        "excluded": excluded,
                        "threshold": cc.threshold,
                    }
                )
            else:
                chapters_summary.append(
                    {
                        "index": idx,
                        "title": chapter.title,
                        "status": "pending",
                    }
                )

        return {
            "book_title": self.book.title,
            "book_author": self.book.author,
            "density": self.density.value,
            "chapters_processed": len(self.chapter_cards),
            "chapters_total": len(self.book.chapters),
            "total_included": total_included,
            "total_excluded": total_excluded,
            "chapters": chapters_summary,
        }

    def export_deck(
        self,
        output_path: Optional[str] = None,
        include_excluded: bool = False,
    ) -> dict:
        """
        Export all processed chapters to an Anki deck.

        Args:
            output_path: Custom output path (uses default if not specified)
            include_excluded: Include excluded cards with 'excluded' tag

        Returns:
            Export results with file paths
        """
        if not self.book:
            raise ValueError("No book loaded.")

        if not self.chapter_cards:
            raise ValueError("No chapters processed yet.")

        # Set up output directory
        if output_path:
            output_dir = Path(output_path)
        else:
            output_dir = self.output_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        # Collect chapter cards in order
        chapter_cards_list = [
            self.chapter_cards[idx]
            for idx in sorted(self.chapter_cards.keys())
        ]

        # Export to JSON
        export_cards_to_json(chapter_cards_list, output_dir, self.book.title)

        # Export to Anki
        deck_name = f"{self.book.title} - {self.book.author}"
        exporter = AnkiExporter(deck_name)

        for cc in chapter_cards_list:
            exporter.add_chapter_cards(cc, include_excluded=include_excluded)

        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in self.book.title
        )
        apkg_path = output_dir / f"{safe_title}.apkg"
        exporter.export(apkg_path)

        return {
            "deck_name": deck_name,
            "apkg_path": str(apkg_path),
            "json_dir": str(output_dir),
            "cards_exported": sum(
                len(cc.included_cards) for cc in chapter_cards_list
            ),
            "cards_excluded": sum(
                len(cc.excluded_cards) for cc in chapter_cards_list
            ),
        }


# Tool definitions for Claude Code SDK integration
AGENT_TOOLS = [
    {
        "name": "load_book",
        "description": "Load an EPUB file and get book information including chapters",
        "parameters": {
            "type": "object",
            "properties": {
                "epub_path": {
                    "type": "string",
                    "description": "Path to the EPUB file",
                }
            },
            "required": ["epub_path"],
        },
    },
    {
        "name": "set_density",
        "description": "Set card generation density (light/medium/thorough)",
        "parameters": {
            "type": "object",
            "properties": {
                "density": {
                    "type": "string",
                    "enum": ["light", "medium", "thorough"],
                    "description": "Card density level",
                }
            },
            "required": ["density"],
        },
    },
    {
        "name": "generate_chapter",
        "description": "Generate flashcards for a specific chapter",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {
                    "type": "integer",
                    "description": "0-indexed chapter number",
                }
            },
            "required": ["chapter_index"],
        },
    },
    {
        "name": "preview_threshold",
        "description": "Preview what a score threshold would include/exclude",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "threshold": {
                    "type": "number",
                    "description": "Score threshold 1-10",
                },
            },
            "required": ["chapter_index", "threshold"],
        },
    },
    {
        "name": "apply_threshold",
        "description": "Apply a score threshold to filter cards",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "threshold": {"type": "number"},
            },
            "required": ["chapter_index", "threshold"],
        },
    },
    {
        "name": "get_cards",
        "description": "Get cards from a chapter with optional filtering",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["included", "excluded"],
                    "description": "Filter by status (omit for all)",
                },
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
            },
            "required": ["chapter_index"],
        },
    },
    {
        "name": "toggle_card",
        "description": "Toggle a card between included/excluded",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "card_id": {"type": "string"},
            },
            "required": ["chapter_index", "card_id"],
        },
    },
    {
        "name": "get_summary",
        "description": "Get summary of all processed chapters",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "export_deck",
        "description": "Export processed chapters to Anki .apkg file",
        "parameters": {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": "Custom output directory",
                },
                "include_excluded": {
                    "type": "boolean",
                    "description": "Include excluded cards with tag",
                },
            },
        },
    },
]


def get_agent_system_prompt() -> str:
    """Get the system prompt for the Claude Code agent."""
    return """You are an AI assistant specialized in creating high-quality Anki flashcard decks from EPUB books.

Your capabilities:
1. Load and analyze EPUB books
2. Generate flashcards using AI (powered by Claude)
3. Rank cards by importance and difficulty
4. Help users filter and curate their decks
5. Export to Anki .apkg format

Workflow:
1. User provides an EPUB file path
2. You load the book and show chapter overview
3. User can process chapters one at a time or in batch
4. For each chapter, you generate cards and show distribution
5. User can adjust thresholds or manually include/exclude cards
6. When satisfied, export to Anki deck

Be helpful and guide users through the process. Explain the card quality metrics and help them find the right threshold for their learning goals.

Card density options:
- light: Core concepts only (~1 card per 2-3 pages) - good for quick overview
- medium: Key ideas + supporting facts (~1 card per page) - balanced approach
- thorough: Comprehensive coverage (~2-3 cards per page) - deep learning

Score thresholds:
- Cards are scored 1-10 based on importance (weighted 2x) and difficulty
- Higher thresholds = fewer but more essential cards
- Recommended: 5-7 for most users, 8+ for essentials only"""
