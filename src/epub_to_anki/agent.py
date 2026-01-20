"""
Claude Code SDK Agent for EPUB to Anki conversion.

This module provides an agent interface that can be used with Claude Code
for interactive book-to-flashcard conversion.
"""

from pathlib import Path
from typing import Optional

from .checkpoint import CheckpointManager, SessionCheckpoint
from .cost_estimator import CostEstimator
from .deduplicator import CardDeduplicator
from .exporter import AnkiExporter
from .exporter.anki_exporter import export_cards_to_json
from .generator import CardGenerator
from .models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardTemplate,
    ChapterCards,
    DeckConfig,
    Density,
)
from .parser import parse_epub
from .ranker import CardRanker


class EpubToAnkiAgent:
    """
    Agent for converting EPUB books to Anki flashcards.

    This agent maintains state across interactions, allowing for:
    - Loading and inspecting books
    - Generating cards chapter by chapter
    - Adjusting thresholds interactively
    - Editing card content with version history
    - Detecting and handling duplicates
    - Resuming interrupted sessions
    - Exporting to Anki format with advanced options:
      - Custom card templates
      - Reverse cards (Answer→Question)
      - Image extraction
      - Chapter subdecks
      - Parent deck nesting
      - Multi-book combining

    Designed to work with Claude Code SDK for rich interactive sessions.
    """

    def __init__(self, api_key: Optional[str] = None, dry_run: bool = False):
        """
        Initialize the agent.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            dry_run: If True, skip API calls and use mock data
        """
        self.dry_run = dry_run
        self.generator = CardGenerator(api_key=api_key) if not dry_run else None
        self.ranker = CardRanker()
        self.cost_estimator = CostEstimator()
        self.deduplicator = CardDeduplicator()

        # Session state
        self.book: Optional[Book] = None
        self.epub_path: Optional[str] = None
        self.chapter_cards: dict[int, ChapterCards] = {}
        self.output_dir: Optional[Path] = None
        self.density = Density.MEDIUM
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.checkpoint: Optional[SessionCheckpoint] = None

        # Advanced config
        self.deck_config = DeckConfig()
        self.chapter_densities: dict[int, Density] = {}

    def _get_safe_title(self, title: str) -> str:
        """Convert title to filesystem-safe string."""
        return "".join(c if c.isalnum() or c in " -_" else "_" for c in title)

    def load_book(
        self,
        epub_path: str,
        check_resume: bool = True,
        extract_images: bool = False,
    ) -> dict:
        """
        Load an EPUB file and return book information.

        Args:
            epub_path: Path to the EPUB file
            check_resume: Check for existing checkpoint to resume
            extract_images: Whether to extract images from the EPUB

        Returns:
            Dict with book metadata, chapter list, and resume info if available
        """
        self.epub_path = epub_path
        self.book = parse_epub(epub_path, extract_images=extract_images)
        self.chapter_cards = {}
        self.deck_config.extract_images = extract_images

        # Set default output directory
        safe_title = self._get_safe_title(self.book.title)
        self.output_dir = Path("output") / safe_title

        # Initialize checkpoint manager
        self.checkpoint_manager = CheckpointManager(self.output_dir)

        result = {
            "title": self.book.title,
            "author": self.book.author,
            "total_chapters": len(self.book.chapters),
            "total_words": self.book.total_words,
            "total_images": len(self.book.images) if extract_images else 0,
            "chapters": [
                {
                    "index": ch.index,
                    "title": ch.title,
                    "word_count": ch.word_count,
                    "image_count": len(ch.images) if extract_images else 0,
                }
                for ch in self.book.chapters
            ],
            "can_resume": False,
        }

        # Check for existing checkpoint
        if check_resume and self.checkpoint_manager.exists():
            existing = self.checkpoint_manager.load()
            if existing and existing.book_title == self.book.title:
                result["can_resume"] = True
                result["resume_info"] = self.checkpoint_manager.get_resume_summary(existing)

        return result

    def resume_session(self) -> dict:
        """
        Resume a previous session from checkpoint.

        Returns:
            Summary of restored session state
        """
        if not self.book:
            raise ValueError("No book loaded. Call load_book first.")

        if not self.checkpoint_manager or not self.checkpoint_manager.exists():
            raise ValueError("No checkpoint found to resume.")

        self.checkpoint = self.checkpoint_manager.load()
        if not self.checkpoint:
            raise ValueError("Failed to load checkpoint.")

        # Restore density setting
        self.density = self.checkpoint.density

        # Restore chapter cards
        restored_chapters = []
        for chapter in self.book.chapters:
            chapter_cards = self.checkpoint_manager.restore_chapter_cards(
                self.checkpoint, chapter
            )
            if chapter_cards:
                self.chapter_cards[chapter.index] = chapter_cards
                restored_chapters.append(chapter.index)

        return {
            "resumed": True,
            "density": self.density.value,
            "chapters_restored": restored_chapters,
            "chapters_remaining": self.checkpoint.get_pending_indices(),
            "total_cards_restored": sum(
                len(cc.cards) for cc in self.chapter_cards.values()
            ),
        }

    def estimate_cost(self, chapter_indices: Optional[list[int]] = None) -> dict:
        """
        Estimate API cost for processing chapters.

        Args:
            chapter_indices: Specific chapters to estimate (None = all remaining)

        Returns:
            Cost estimate with breakdown
        """
        if not self.book:
            raise ValueError("No book loaded. Call load_book first.")

        # If no indices specified, estimate for unprocessed chapters
        if chapter_indices is None:
            chapter_indices = [
                ch.index
                for ch in self.book.chapters
                if ch.index not in self.chapter_cards
            ]

        estimate = self.cost_estimator.estimate_book(
            self.book, self.density, chapter_indices
        )

        return {
            "estimated_cost_usd": estimate.estimated_cost_usd,
            "total_input_tokens": estimate.total_input_tokens,
            "total_output_tokens": estimate.total_output_tokens,
            "chapters_count": estimate.chapters_count,
            "total_words": estimate.total_words,
            "density": estimate.density,
            "per_chapter": [
                {
                    "chapter_index": ch["chapter_index"],
                    "chapter_title": ch["chapter_title"],
                    "estimated_cards": ch["estimated_cards"],
                    "input_tokens": ch["input_tokens"],
                    "output_tokens": ch["output_tokens"],
                }
                for ch in estimate.chapter_estimates
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

    def set_chapter_density(self, chapter_index: int, density: str) -> dict:
        """
        Set density for a specific chapter.

        Args:
            chapter_index: 0-indexed chapter number
            density: One of 'light', 'medium', 'thorough'

        Returns:
            Confirmation of the setting
        """
        density_enum = Density(density)
        self.chapter_densities[chapter_index] = density_enum

        return {
            "chapter_index": chapter_index,
            "density": density,
            "message": f"Chapter {chapter_index + 1} will use {density} density",
        }

    def get_chapter_density(self, chapter_index: int) -> str:
        """Get the density setting for a specific chapter."""
        density = self.chapter_densities.get(chapter_index, self.density)
        return density.value

    def configure_deck(
        self,
        parent_deck: Optional[str] = None,
        create_subdecks: bool = False,
        include_reverse: bool = False,
        extract_images: bool = False,
    ) -> dict:
        """
        Configure deck export options.

        Args:
            parent_deck: Parent deck name for nesting
            create_subdecks: Create per-chapter subdecks
            include_reverse: Generate reverse (A→Q) cards
            extract_images: Include images in deck

        Returns:
            Current deck configuration
        """
        self.deck_config.parent_deck = parent_deck
        self.deck_config.create_subdecks = create_subdecks
        self.deck_config.include_reverse = include_reverse
        self.deck_config.extract_images = extract_images

        return {
            "parent_deck": parent_deck,
            "create_subdecks": create_subdecks,
            "include_reverse": include_reverse,
            "extract_images": extract_images,
        }

    def set_custom_template(
        self,
        template_type: str,
        front_html: str,
        back_html: str,
        css: str,
    ) -> dict:
        """
        Set a custom card template.

        Args:
            template_type: 'qa' or 'cloze'
            front_html: HTML for card front
            back_html: HTML for card back
            css: CSS styling

        Returns:
            Confirmation of template set
        """
        template = CardTemplate(
            name=f"custom_{template_type}",
            front_html=front_html,
            back_html=back_html,
            css=css,
        )

        if template_type == "qa":
            self.deck_config.qa_template = template
        else:
            self.deck_config.cloze_template = template

        return {
            "template_type": template_type,
            "template_set": True,
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

        if chapter_index < 0 or chapter_index >= len(self.book.chapters):
            raise ValueError(f"Invalid chapter index: {chapter_index}")

        chapter = self.book.chapters[chapter_index]

        # Get chapter-specific density
        chapter_density = self.chapter_densities.get(chapter_index, self.density)

        if self.dry_run:
            # Generate mock cards for dry run mode
            chapter_cards = self._generate_mock_cards(chapter)
        else:
            chapter_cards = self.generator.generate_for_chapter(
                self.book, chapter, chapter_density
            )

        # Rank cards
        self.ranker.rank_chapter(chapter_cards)

        # Store in session
        self.chapter_cards[chapter_index] = chapter_cards

        # Save checkpoint
        self._save_checkpoint()

        # Get statistics
        stats = self.ranker.get_score_distribution(chapter_cards)

        return {
            "chapter_index": chapter_index,
            "chapter_title": chapter.title,
            "total_cards": len(chapter_cards.cards),
            "density_used": chapter_density.value,
            "score_distribution": stats,
            "dry_run": self.dry_run,
            "sample_cards": [
                {
                    "id": c.id,
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

    def _generate_mock_cards(self, chapter) -> ChapterCards:
        """Generate mock cards for dry run mode."""
        import uuid

        from .models import CardType

        # Get chapter-specific density
        chapter_density = self.chapter_densities.get(chapter.index, self.density)

        # Create a few mock cards based on chapter length
        num_cards = max(1, chapter.word_count // 500)

        mock_cards = []
        for i in range(num_cards):
            card = Card(
                id=str(uuid.uuid4())[:8],
                format=CardFormat.QA,
                card_type=CardType.CONCEPT,
                question=f"[DRY RUN] Sample question {i+1} from {chapter.title}?",
                answer=f"[DRY RUN] Sample answer {i+1}",
                importance=5 + (i % 5),
                difficulty=3 + (i % 5),
                source_chapter=chapter.title,
                source_chapter_index=chapter.index,
                status=CardStatus.INCLUDED,
                tags=[f"chapter::{chapter.index + 1}", "dry_run"],
            )
            mock_cards.append(card)

        return ChapterCards(
            chapter=chapter,
            cards=mock_cards,
            density_used=chapter_density,
        )

    def _save_checkpoint(self) -> None:
        """Save current session to checkpoint."""
        if not self.checkpoint_manager or not self.book or not self.epub_path:
            return

        if not self.checkpoint:
            self.checkpoint = self.checkpoint_manager.create_checkpoint(
                epub_path=self.epub_path,
                book_title=self.book.title,
                book_author=self.book.author,
                total_chapters=len(self.book.chapters),
                density=self.density,
            )

        # Update checkpoint with all current chapter cards
        for chapter_cards in self.chapter_cards.values():
            self.checkpoint_manager.add_chapter(self.checkpoint, chapter_cards)

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

        # Update checkpoint
        self._save_checkpoint()

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
        chapter_density = self.chapter_densities.get(chapter_index, self.density)
        self.ranker.apply_density_threshold(chapter_cards, chapter_density)

        # Update checkpoint
        self._save_checkpoint()

        return {
            "chapter_index": chapter_index,
            "density": chapter_density.value,
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
                    "is_reverse": c.is_reverse,
                    "version_count": len(c.version_history),
                }
                for c in cards
            ],
        }

    def get_card(self, chapter_index: int, card_id: str) -> dict:
        """
        Get a single card by ID.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card

        Returns:
            Full card details
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                return {
                    "id": card.id,
                    "format": card.format.value,
                    "type": card.card_type.value,
                    "question": card.question,
                    "answer": card.answer,
                    "cloze_text": card.cloze_text,
                    "importance": card.importance,
                    "difficulty": card.difficulty,
                    "score": round(card.compute_score(), 1),
                    "status": card.status.value,
                    "source_chapter": card.source_chapter,
                    "source_section": card.source_section,
                    "source_quote": card.source_quote,
                    "tags": card.tags,
                    "is_reverse": card.is_reverse,
                    "original_card_id": card.original_card_id,
                    "created_at": card.created_at.isoformat(),
                    "updated_at": card.updated_at.isoformat(),
                    "version_count": len(card.version_history),
                }

        raise ValueError(f"Card {card_id} not found")

    def get_card_versions(self, chapter_index: int, card_id: str) -> dict:
        """
        Get version history for a card.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card

        Returns:
            List of versions with content snapshots
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                return {
                    "card_id": card_id,
                    "current_version": len(card.version_history) + 1,
                    "versions": [
                        {
                            "version": v.version,
                            "timestamp": v.timestamp.isoformat(),
                            "question": v.question,
                            "answer": v.answer,
                            "cloze_text": v.cloze_text,
                            "importance": v.importance,
                            "difficulty": v.difficulty,
                            "editor_note": v.editor_note,
                        }
                        for v in card.version_history
                    ],
                }

        raise ValueError(f"Card {card_id} not found")

    def edit_card(
        self,
        chapter_index: int,
        card_id: str,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        cloze_text: Optional[str] = None,
        importance: Optional[int] = None,
        difficulty: Optional[int] = None,
        save_version: bool = True,
        editor_note: Optional[str] = None,
    ) -> dict:
        """
        Edit a card's content with optional version tracking.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card to edit
            question: New question text (for QA cards)
            answer: New answer text (for QA cards)
            cloze_text: New cloze text (for cloze cards)
            importance: New importance score (1-10)
            difficulty: New difficulty score (1-10)
            save_version: Whether to save current state to version history
            editor_note: Note about this edit

        Returns:
            Updated card details
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                # Save version before editing if requested
                if save_version:
                    card.save_version(editor_note)

                # Update fields if provided
                if card.format == CardFormat.QA:
                    if question is not None:
                        card.question = question
                    if answer is not None:
                        card.answer = answer
                else:
                    if cloze_text is not None:
                        card.cloze_text = cloze_text

                if importance is not None:
                    card.importance = max(1, min(10, importance))
                if difficulty is not None:
                    card.difficulty = max(1, min(10, difficulty))

                # Update checkpoint
                self._save_checkpoint()

                return {
                    "card_id": card_id,
                    "updated": True,
                    "new_content": card.get_display_text(),
                    "new_score": round(card.compute_score(), 1),
                    "version_count": len(card.version_history),
                }

        raise ValueError(f"Card {card_id} not found")

    def restore_card_version(
        self,
        chapter_index: int,
        card_id: str,
        version_number: int,
    ) -> dict:
        """
        Restore a card to a previous version.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card
            version_number: Version to restore (1-indexed)

        Returns:
            Restored card details
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                if card.restore_version(version_number):
                    self._save_checkpoint()
                    return {
                        "card_id": card_id,
                        "restored_to": version_number,
                        "new_content": card.get_display_text(),
                        "version_count": len(card.version_history),
                    }
                else:
                    raise ValueError(f"Version {version_number} not found")

        raise ValueError(f"Card {card_id} not found")

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

                # Update checkpoint
                self._save_checkpoint()

                return {
                    "card_id": card_id,
                    "new_status": card.status.value,
                }

        raise ValueError(f"Card {card_id} not found")

    def create_reverse_card(self, chapter_index: int, card_id: str) -> dict:
        """
        Create a reverse card for a specific Q&A card.

        Args:
            chapter_index: Chapter containing the card
            card_id: ID of the card to reverse

        Returns:
            Details of the created reverse card
        """
        if chapter_index not in self.chapter_cards:
            raise ValueError(f"Chapter {chapter_index} not generated yet.")

        for card in self.chapter_cards[chapter_index].cards:
            if card.id == card_id:
                reverse = card.create_reverse()
                if reverse:
                    # Add reverse card to chapter
                    self.chapter_cards[chapter_index].cards.append(reverse)
                    self._save_checkpoint()

                    return {
                        "created": True,
                        "reverse_id": reverse.id,
                        "content": reverse.get_display_text(),
                    }
                else:
                    return {
                        "created": False,
                        "reason": "Only Q&A cards can be reversed",
                    }

        raise ValueError(f"Card {card_id} not found")

    def find_duplicates(
        self,
        similarity_threshold: float = 0.85,
        cross_chapter: bool = True,
    ) -> dict:
        """
        Find duplicate or similar cards.

        Args:
            similarity_threshold: Minimum similarity to consider as duplicate (0-1)
            cross_chapter: Check across chapters (True) or only within chapters (False)

        Returns:
            Duplicate detection results
        """
        if not self.chapter_cards:
            raise ValueError("No chapters processed yet.")

        # Collect all cards
        all_cards = []
        for cc in self.chapter_cards.values():
            all_cards.extend(cc.cards)

        # Set threshold and find duplicates
        self.deduplicator.similarity_threshold = similarity_threshold
        result = self.deduplicator.find_duplicates(all_cards, cross_chapter)

        return {
            "total_cards": result.total_cards,
            "unique_cards": result.unique_cards,
            "duplicates_found": result.duplicates_found,
            "exact_duplicates": result.exact_duplicates,
            "similar_duplicates": result.similar_duplicates,
            "duplicate_groups": [
                {
                    "primary": {
                        "id": g.primary_card.id,
                        "chapter_index": g.primary_card.source_chapter_index,
                        "content": g.primary_card.get_display_text()[:100],
                    },
                    "duplicates": [
                        {
                            "id": d.id,
                            "chapter_index": d.source_chapter_index,
                            "similarity": round(s, 2),
                            "content": d.get_display_text()[:100],
                        }
                        for d, s in zip(g.duplicates, g.similarity_scores)
                    ],
                }
                for g in result.duplicate_groups[:10]  # Limit to first 10 groups
            ],
        }

    def remove_duplicates(
        self,
        keep_strategy: str = "highest_score",
    ) -> dict:
        """
        Remove duplicate cards, keeping one from each group.

        Args:
            keep_strategy: How to choose which card to keep:
                - "highest_score": Keep card with highest computed score
                - "first": Keep the first card found
                - "highest_importance": Keep card with highest importance

        Returns:
            Summary of removed duplicates
        """
        if not self.chapter_cards:
            raise ValueError("No chapters processed yet.")

        # Find duplicates first
        all_cards = []
        for cc in self.chapter_cards.values():
            all_cards.extend(cc.cards)

        result = self.deduplicator.find_duplicates(all_cards, cross_chapter=True)

        # Mark duplicates as excluded
        excluded_count = self.deduplicator.mark_duplicates_excluded(
            result, keep_strategy
        )

        # Update checkpoint
        self._save_checkpoint()

        return {
            "duplicates_removed": excluded_count,
            "keep_strategy": keep_strategy,
            "groups_processed": len(result.duplicate_groups),
        }

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

                # Count reverse cards
                reverse_count = sum(1 for c in cc.cards if c.is_reverse)

                chapters_summary.append(
                    {
                        "index": idx,
                        "title": chapter.title,
                        "status": "processed",
                        "included": included,
                        "excluded": excluded,
                        "reverse_cards": reverse_count,
                        "threshold": cc.threshold,
                        "density_used": cc.density_used.value,
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
            "dry_run": self.dry_run,
            "chapters_processed": len(self.chapter_cards),
            "chapters_total": len(self.book.chapters),
            "total_included": total_included,
            "total_excluded": total_excluded,
            "deck_config": {
                "parent_deck": self.deck_config.parent_deck,
                "create_subdecks": self.deck_config.create_subdecks,
                "include_reverse": self.deck_config.include_reverse,
                "extract_images": self.deck_config.extract_images,
            },
            "chapters": chapters_summary,
        }

    def clear_checkpoint(self) -> dict:
        """
        Delete the checkpoint file.

        Returns:
            Confirmation of deletion
        """
        if self.checkpoint_manager and self.checkpoint_manager.delete():
            self.checkpoint = None
            return {"deleted": True, "message": "Checkpoint deleted successfully"}
        return {"deleted": False, "message": "No checkpoint to delete"}

    def export_deck(
        self,
        output_path: Optional[str] = None,
        include_excluded: bool = False,
        generate_reverse: bool = False,
    ) -> dict:
        """
        Export all processed chapters to an Anki deck.

        Args:
            output_path: Custom output path (uses default if not specified)
            include_excluded: Include excluded cards with 'excluded' tag
            generate_reverse: Generate reverse cards for all Q&A cards

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
        deck_name = self.deck_config.get_full_deck_name(
            self.book.title, self.book.author
        )
        exporter = AnkiExporter(deck_name, config=self.deck_config)

        for cc in chapter_cards_list:
            exporter.add_chapter_cards(
                cc,
                include_excluded=include_excluded,
                generate_reverse=generate_reverse,
            )

        # Add images if configured
        if self.deck_config.extract_images and self.book.images:
            temp_media_dir = output_dir / ".media"
            exporter.add_images(self.book.images, temp_media_dir)

        safe_title = self._get_safe_title(self.book.title)
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
            "images_included": len(self.book.images) if self.deck_config.extract_images else 0,
            "subdecks_created": len(exporter.subdecks) if self.deck_config.create_subdecks else 0,
        }


# Tool definitions for Claude Code SDK integration
AGENT_TOOLS = [
    {
        "name": "load_book",
        "description": (
            "Load an EPUB file and get book information including chapters. "
            "Checks for existing checkpoint to resume."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "epub_path": {
                    "type": "string",
                    "description": "Path to the EPUB file",
                },
                "check_resume": {
                    "type": "boolean",
                    "description": "Check for existing checkpoint (default: true)",
                },
                "extract_images": {
                    "type": "boolean",
                    "description": "Extract images from EPUB (default: false)",
                },
            },
            "required": ["epub_path"],
        },
    },
    {
        "name": "resume_session",
        "description": (
            "Resume a previous session from checkpoint. "
            "Call after load_book if can_resume is true."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "estimate_cost",
        "description": "Estimate API cost before generation. Shows token and cost breakdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Specific chapters to estimate (omit for all remaining)",
                },
            },
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
        "name": "set_chapter_density",
        "description": "Set density for a specific chapter (overrides default)",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "density": {
                    "type": "string",
                    "enum": ["light", "medium", "thorough"],
                },
            },
            "required": ["chapter_index", "density"],
        },
    },
    {
        "name": "configure_deck",
        "description": (
            "Configure deck export options (parent deck, subdecks, reverse cards, images)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "parent_deck": {
                    "type": "string",
                    "description": "Parent deck name for nesting",
                },
                "create_subdecks": {
                    "type": "boolean",
                    "description": "Create per-chapter subdecks",
                },
                "include_reverse": {
                    "type": "boolean",
                    "description": "Generate reverse (A->Q) cards",
                },
                "extract_images": {
                    "type": "boolean",
                    "description": "Include images in deck",
                },
            },
        },
    },
    {
        "name": "set_custom_template",
        "description": "Set a custom HTML/CSS template for cards",
        "parameters": {
            "type": "object",
            "properties": {
                "template_type": {
                    "type": "string",
                    "enum": ["qa", "cloze"],
                },
                "front_html": {"type": "string"},
                "back_html": {"type": "string"},
                "css": {"type": "string"},
            },
            "required": ["template_type", "front_html", "back_html", "css"],
        },
    },
    {
        "name": "generate_chapter",
        "description": "Generate flashcards for a specific chapter. Progress is auto-saved.",
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
        "name": "apply_auto_threshold",
        "description": "Apply automatic density-based threshold to a chapter",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
            },
            "required": ["chapter_index"],
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
        "name": "get_card",
        "description": "Get full details of a single card",
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
        "name": "get_card_versions",
        "description": "Get version history for a card",
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
        "name": "edit_card",
        "description": "Edit a card's content with optional version tracking",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "card_id": {"type": "string"},
                "question": {"type": "string"},
                "answer": {"type": "string"},
                "cloze_text": {"type": "string"},
                "importance": {"type": "integer"},
                "difficulty": {"type": "integer"},
                "save_version": {"type": "boolean", "default": True},
                "editor_note": {"type": "string"},
            },
            "required": ["chapter_index", "card_id"],
        },
    },
    {
        "name": "restore_card_version",
        "description": "Restore a card to a previous version",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_index": {"type": "integer"},
                "card_id": {"type": "string"},
                "version_number": {"type": "integer"},
            },
            "required": ["chapter_index", "card_id", "version_number"],
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
        "name": "create_reverse_card",
        "description": "Create a reverse (A->Q) card for a specific Q&A card",
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
        "name": "find_duplicates",
        "description": "Find duplicate or similar cards across chapters",
        "parameters": {
            "type": "object",
            "properties": {
                "similarity_threshold": {
                    "type": "number",
                    "description": "Similarity threshold 0-1 (default: 0.85)",
                },
                "cross_chapter": {
                    "type": "boolean",
                    "description": "Check across chapters (default: true)",
                },
            },
        },
    },
    {
        "name": "remove_duplicates",
        "description": "Mark duplicate cards as excluded, keeping one from each group",
        "parameters": {
            "type": "object",
            "properties": {
                "keep_strategy": {
                    "type": "string",
                    "enum": ["highest_score", "first", "highest_importance"],
                    "description": "How to choose which card to keep",
                },
            },
        },
    },
    {
        "name": "get_summary",
        "description": "Get summary of all processed chapters",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_checkpoint",
        "description": "Delete the checkpoint file to start fresh",
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
                "generate_reverse": {
                    "type": "boolean",
                    "description": "Generate reverse cards for all Q&A",
                },
            },
        },
    },
]


def get_agent_system_prompt() -> str:
    """Get the system prompt for the Claude Code agent."""
    return """\
You are an AI assistant specialized in creating high-quality Anki flashcard decks from EPUB books.

Your capabilities:
1. Load and analyze EPUB books (with optional image extraction)
2. Estimate API costs before generation
3. Resume interrupted sessions (auto-checkpointing)
4. Generate flashcards using AI (powered by Claude)
5. Rank cards by importance and difficulty
6. Edit card content with version history (save_version, restore_version)
7. Detect and remove duplicate cards
8. Help users filter and curate their decks
9. Export to Anki .apkg format with advanced options:
   - Custom HTML/CSS templates for Q&A and Cloze cards
   - Reverse cards (Answer->Question) for bidirectional learning
   - Image extraction and embedding
   - Per-chapter subdecks for hierarchical organization
   - Parent deck nesting for library organization
   - Multi-book combining

Workflow:
1. User provides an EPUB file path
2. You load the book and check for existing checkpoint
3. Show cost estimate before generation
4. User can configure per-chapter density if needed
5. User can set up deck options (subdecks, reverse, parent)
6. Process chapters one at a time or in batch
7. Progress is auto-saved after each chapter
8. For each chapter, generate cards and show distribution
9. User can adjust thresholds, edit cards with versioning
10. Check for duplicates before export
11. When satisfied, export to Anki deck

Card density options:
- light: Core concepts only (~1 card per 2-3 pages) - good for quick overview
- medium: Key ideas + supporting facts (~1 card per page) - balanced approach
- thorough: Comprehensive coverage (~2-3 cards per page) - deep learning

Score thresholds:
- Cards are scored 1-10 based on importance (weighted 2x) and difficulty
- Higher thresholds = fewer but more essential cards
- Recommended: 5-7 for most users, 8+ for essentials only

Advanced features:
- Custom templates: set_custom_template() for personalized card styling
- Per-chapter density: set_chapter_density() for varying detail by chapter
- Version history: edit_card() with save_version=True, get_card_versions()
- Reverse cards: configure_deck(include_reverse=True) or create_reverse_card()
- Subdecks: configure_deck(create_subdecks=True) for chapter organization
- Parent deck: configure_deck(parent_deck="My Library") for nesting
- Images: load_book(extract_images=True) to embed EPUB images

Dry run mode:
- Use dry_run=True to test the workflow without making API calls
- Generates mock cards to validate the process"""
