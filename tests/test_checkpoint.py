"""Tests for checkpoint/resume functionality."""

import tempfile
from pathlib import Path

from epub_to_anki.checkpoint import (
    ChapterCheckpoint,
    CheckpointManager,
    SessionCheckpoint,
)
from epub_to_anki.models import (
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    Density,
)


def create_test_card(id: str, chapter_index: int = 0) -> Card:
    """Helper to create test cards."""
    return Card(
        id=id,
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question=f"Question {id}",
        answer=f"Answer {id}",
        importance=5,
        difficulty=5,
        source_chapter=f"Chapter {chapter_index + 1}",
        source_chapter_index=chapter_index,
        status=CardStatus.INCLUDED,
    )


def create_test_chapter(index: int) -> Chapter:
    """Helper to create test chapters."""
    return Chapter(
        index=index,
        title=f"Chapter {index + 1}",
        content=f"Content for chapter {index + 1}",
        word_count=1000,
    )


def create_test_chapter_cards(chapter_index: int, num_cards: int = 3) -> ChapterCards:
    """Helper to create ChapterCards."""
    chapter = create_test_chapter(chapter_index)
    cards = [create_test_card(f"{chapter_index}_{i}", chapter_index) for i in range(num_cards)]
    return ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)


class TestSessionCheckpoint:
    """Tests for SessionCheckpoint model."""

    def test_create_checkpoint(self):
        """Test creating a session checkpoint."""
        checkpoint = SessionCheckpoint(
            epub_path="/path/to/book.epub",
            book_title="Test Book",
            book_author="Test Author",
            total_chapters=5,
            density=Density.MEDIUM,
        )

        assert checkpoint.book_title == "Test Book"
        assert checkpoint.total_chapters == 5
        assert len(checkpoint.chapters_processed) == 0

    def test_is_chapter_processed(self):
        """Test checking if chapter is processed."""
        checkpoint = SessionCheckpoint(
            epub_path="/path/to/book.epub",
            book_title="Test Book",
            book_author="Test Author",
            total_chapters=5,
            density=Density.MEDIUM,
        )

        assert not checkpoint.is_chapter_processed(0)

        # Add a chapter checkpoint
        checkpoint.chapters_processed[0] = ChapterCheckpoint(
            chapter_index=0,
            chapter_title="Chapter 1",
            cards=[],
            density_used=Density.MEDIUM,
        )

        assert checkpoint.is_chapter_processed(0)
        assert not checkpoint.is_chapter_processed(1)

    def test_get_processed_indices(self):
        """Test getting processed chapter indices."""
        checkpoint = SessionCheckpoint(
            epub_path="/path/to/book.epub",
            book_title="Test Book",
            book_author="Test Author",
            total_chapters=5,
            density=Density.MEDIUM,
        )

        checkpoint.chapters_processed[2] = ChapterCheckpoint(
            chapter_index=2,
            chapter_title="Chapter 3",
            cards=[],
            density_used=Density.MEDIUM,
        )
        checkpoint.chapters_processed[0] = ChapterCheckpoint(
            chapter_index=0,
            chapter_title="Chapter 1",
            cards=[],
            density_used=Density.MEDIUM,
        )

        indices = checkpoint.get_processed_indices()
        assert indices == [0, 2]

    def test_get_pending_indices(self):
        """Test getting pending chapter indices."""
        checkpoint = SessionCheckpoint(
            epub_path="/path/to/book.epub",
            book_title="Test Book",
            book_author="Test Author",
            total_chapters=3,
            density=Density.MEDIUM,
        )

        checkpoint.chapters_processed[1] = ChapterCheckpoint(
            chapter_index=1,
            chapter_title="Chapter 2",
            cards=[],
            density_used=Density.MEDIUM,
        )

        pending = checkpoint.get_pending_indices()
        assert pending == [0, 2]


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_exists_no_checkpoint(self):
        """Test exists returns False when no checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            assert not manager.exists()

    def test_create_and_save_checkpoint(self):
        """Test creating and saving a checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )

            path = manager.save(checkpoint)

            assert path.exists()
            assert manager.exists()

    def test_load_checkpoint(self):
        """Test loading a saved checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            # Create and save
            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )
            manager.save(checkpoint)

            # Load
            loaded = manager.load()

            assert loaded is not None
            assert loaded.book_title == "Test Book"
            assert loaded.density == Density.MEDIUM

    def test_add_chapter(self):
        """Test adding a chapter to checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )

            chapter_cards = create_test_chapter_cards(0, 3)
            manager.add_chapter(checkpoint, chapter_cards)

            assert 0 in checkpoint.chapters_processed
            assert len(checkpoint.chapters_processed[0].cards) == 3

    def test_restore_chapter_cards(self):
        """Test restoring chapter cards from checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )

            # Add a chapter
            original_chapter_cards = create_test_chapter_cards(0, 3)
            manager.add_chapter(checkpoint, original_chapter_cards)
            manager.save(checkpoint)

            # Load and restore
            loaded = manager.load()
            chapter = create_test_chapter(0)
            restored = manager.restore_chapter_cards(loaded, chapter)

            assert restored is not None
            assert len(restored.cards) == 3
            assert restored.density_used == Density.MEDIUM

    def test_restore_missing_chapter(self):
        """Test restoring a chapter that doesn't exist in checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )
            manager.save(checkpoint)

            loaded = manager.load()
            chapter = create_test_chapter(0)
            restored = manager.restore_chapter_cards(loaded, chapter)

            assert restored is None

    def test_delete_checkpoint(self):
        """Test deleting a checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )
            manager.save(checkpoint)

            assert manager.exists()
            assert manager.delete()
            assert not manager.exists()

    def test_delete_nonexistent_checkpoint(self):
        """Test deleting when no checkpoint exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            assert not manager.delete()

    def test_get_resume_summary(self):
        """Test getting resume summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            checkpoint = manager.create_checkpoint(
                epub_path="/path/to/book.epub",
                book_title="Test Book",
                book_author="Test Author",
                total_chapters=5,
                density=Density.MEDIUM,
            )

            # Add some chapters
            manager.add_chapter(checkpoint, create_test_chapter_cards(0, 3))
            manager.add_chapter(checkpoint, create_test_chapter_cards(1, 2))

            summary = manager.get_resume_summary(checkpoint)

            assert summary["book_title"] == "Test Book"
            assert summary["chapters_processed"] == 2
            assert summary["chapters_total"] == 5
            assert summary["chapters_remaining"] == 3
            assert summary["total_cards_generated"] == 5
