"""Checkpoint and resume support for long-running card generation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import Card, Chapter, ChapterCards, Density


class ChapterCheckpoint(BaseModel):
    """Checkpoint data for a single chapter."""

    chapter_index: int
    chapter_title: str
    cards: list[Card]
    density_used: Density
    threshold: Optional[float] = None
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SessionCheckpoint(BaseModel):
    """Full session checkpoint for resume support."""

    version: str = "1.0"
    epub_path: str
    book_title: str
    book_author: str
    total_chapters: int
    density: Density
    chapters_processed: dict[int, ChapterCheckpoint] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def is_chapter_processed(self, chapter_index: int) -> bool:
        """Check if a chapter has been processed."""
        return chapter_index in self.chapters_processed

    def get_processed_indices(self) -> list[int]:
        """Get list of processed chapter indices."""
        return sorted(self.chapters_processed.keys())

    def get_pending_indices(self) -> list[int]:
        """Get list of chapters not yet processed."""
        return [i for i in range(self.total_chapters) if i not in self.chapters_processed]


class CheckpointManager:
    """Manages saving and loading of session checkpoints."""

    CHECKPOINT_FILENAME = "checkpoint.json"

    def __init__(self, output_dir: Path):
        """
        Initialize checkpoint manager.

        Args:
            output_dir: Directory to store checkpoint file
        """
        self.output_dir = Path(output_dir)
        self.checkpoint_path = self.output_dir / self.CHECKPOINT_FILENAME

    def exists(self) -> bool:
        """Check if a checkpoint exists."""
        return self.checkpoint_path.exists()

    def load(self) -> Optional[SessionCheckpoint]:
        """
        Load existing checkpoint if available.

        Returns:
            SessionCheckpoint if found, None otherwise
        """
        if not self.exists():
            return None

        try:
            data = json.loads(self.checkpoint_path.read_text())
            return SessionCheckpoint(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    def save(self, checkpoint: SessionCheckpoint) -> Path:
        """
        Save checkpoint to disk.

        Args:
            checkpoint: SessionCheckpoint to save

        Returns:
            Path to saved checkpoint file
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint.updated_at = datetime.now().isoformat()
        self.checkpoint_path.write_text(checkpoint.model_dump_json(indent=2))
        return self.checkpoint_path

    def create_checkpoint(
        self,
        epub_path: str,
        book_title: str,
        book_author: str,
        total_chapters: int,
        density: Density,
    ) -> SessionCheckpoint:
        """
        Create a new session checkpoint.

        Args:
            epub_path: Path to the EPUB file
            book_title: Title of the book
            book_author: Author of the book
            total_chapters: Total number of chapters
            density: Card generation density

        Returns:
            New SessionCheckpoint
        """
        return SessionCheckpoint(
            epub_path=epub_path,
            book_title=book_title,
            book_author=book_author,
            total_chapters=total_chapters,
            density=density,
        )

    def add_chapter(
        self,
        checkpoint: SessionCheckpoint,
        chapter_cards: ChapterCards,
    ) -> SessionCheckpoint:
        """
        Add a processed chapter to the checkpoint.

        Args:
            checkpoint: Current checkpoint
            chapter_cards: Processed chapter cards

        Returns:
            Updated checkpoint
        """
        chapter_checkpoint = ChapterCheckpoint(
            chapter_index=chapter_cards.chapter.index,
            chapter_title=chapter_cards.chapter.title,
            cards=chapter_cards.cards,
            density_used=chapter_cards.density_used,
            threshold=chapter_cards.threshold,
        )
        checkpoint.chapters_processed[chapter_cards.chapter.index] = chapter_checkpoint
        self.save(checkpoint)
        return checkpoint

    def restore_chapter_cards(
        self,
        checkpoint: SessionCheckpoint,
        chapter: Chapter,
    ) -> Optional[ChapterCards]:
        """
        Restore ChapterCards from checkpoint.

        Args:
            checkpoint: Session checkpoint
            chapter: Chapter object to restore cards for

        Returns:
            ChapterCards if found in checkpoint, None otherwise
        """
        if chapter.index not in checkpoint.chapters_processed:
            return None

        chapter_checkpoint = checkpoint.chapters_processed[chapter.index]
        return ChapterCards(
            chapter=chapter,
            cards=chapter_checkpoint.cards,
            density_used=chapter_checkpoint.density_used,
            threshold=chapter_checkpoint.threshold,
        )

    def delete(self) -> bool:
        """
        Delete checkpoint file.

        Returns:
            True if deleted, False if didn't exist
        """
        if self.exists():
            self.checkpoint_path.unlink()
            return True
        return False

    def get_resume_summary(self, checkpoint: SessionCheckpoint) -> dict:
        """
        Get a summary of what can be resumed.

        Args:
            checkpoint: Checkpoint to summarize

        Returns:
            Dict with resume information
        """
        processed = len(checkpoint.chapters_processed)
        total = checkpoint.total_chapters
        total_cards = sum(
            len(cc.cards) for cc in checkpoint.chapters_processed.values()
        )

        return {
            "book_title": checkpoint.book_title,
            "book_author": checkpoint.book_author,
            "density": checkpoint.density.value,
            "chapters_processed": processed,
            "chapters_total": total,
            "chapters_remaining": total - processed,
            "total_cards_generated": total_cards,
            "created_at": checkpoint.created_at,
            "updated_at": checkpoint.updated_at,
        }
