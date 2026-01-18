"""Tests for card versioning."""

import pytest
from datetime import datetime

from epub_to_anki.models import (
    Card,
    CardFormat,
    CardStatus,
    CardType,
    CardVersion,
)


def create_test_card() -> Card:
    """Create a test card."""
    return Card(
        id="test-card-1",
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question="What is photosynthesis?",
        answer="The process by which plants convert light to energy",
        importance=8,
        difficulty=5,
        source_chapter="Chapter 1",
        source_chapter_index=0,
    )


class TestCardVersion:
    """Test CardVersion model."""

    def test_create_card_version(self):
        """Test creating a card version."""
        version = CardVersion(
            version=1,
            question="Original question",
            answer="Original answer",
            importance=7,
            difficulty=4,
            change_reason="Initial version",
        )
        assert version.version == 1
        assert version.question == "Original question"
        assert version.timestamp is not None

    def test_card_version_timestamp_auto(self):
        """Test that timestamp is automatically set."""
        version = CardVersion(version=1)
        assert version.timestamp is not None
        # Verify it's a valid ISO format
        datetime.fromisoformat(version.timestamp)


class TestCardVersioning:
    """Test card versioning functionality."""

    def test_initial_version(self):
        """Test that cards start at version 1."""
        card = create_test_card()
        assert card.version == 1
        assert len(card.version_history) == 0

    def test_save_version(self):
        """Test saving a version before changes."""
        card = create_test_card()
        original_question = card.question

        # Save version
        card.save_version(change_reason="Improving question")

        # Version should increment
        assert card.version == 2

        # History should contain original values
        assert len(card.version_history) == 1
        assert card.version_history[0].version == 1
        assert card.version_history[0].question == original_question
        assert card.version_history[0].change_reason == "Improving question"

    def test_multiple_versions(self):
        """Test saving multiple versions."""
        card = create_test_card()

        # First edit
        card.save_version("First edit")
        card.question = "Updated question v2"

        # Second edit
        card.save_version("Second edit")
        card.question = "Updated question v3"

        assert card.version == 3
        assert len(card.version_history) == 2
        assert card.version_history[0].version == 1
        assert card.version_history[1].version == 2

    def test_version_preserves_all_fields(self):
        """Test that version saves all editable fields."""
        card = create_test_card()

        card.save_version()

        history = card.version_history[0]
        assert history.question == "What is photosynthesis?"
        assert history.answer == "The process by which plants convert light to energy"
        assert history.importance == 8
        assert history.difficulty == 5
        assert history.cloze_text is None  # QA card has no cloze text

    def test_cloze_card_versioning(self):
        """Test versioning works for cloze cards."""
        card = Card(
            id="cloze-1",
            format=CardFormat.CLOZE,
            card_type=CardType.TERM,
            cloze_text="{{c1::Photosynthesis}} converts light to energy",
            importance=7,
            difficulty=4,
            source_chapter="Chapter 1",
            source_chapter_index=0,
        )

        original_cloze = card.cloze_text
        card.save_version("Improving cloze")
        card.cloze_text = "{{c1::Photosynthesis}} is the process of {{c2::energy}} conversion"

        assert card.version == 2
        assert card.version_history[0].cloze_text == original_cloze

    def test_updated_at_changes(self):
        """Test that updated_at is updated when saving version."""
        card = create_test_card()
        original_updated = card.updated_at

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        card.save_version()

        assert card.updated_at != original_updated

    def test_created_at_unchanged(self):
        """Test that created_at doesn't change."""
        card = create_test_card()
        original_created = card.created_at

        card.save_version()
        card.save_version()

        assert card.created_at == original_created

    def test_version_history_order(self):
        """Test that version history is in chronological order."""
        card = create_test_card()

        for i in range(5):
            card.save_version(f"Edit {i+1}")

        # Versions should be 1, 2, 3, 4, 5
        for i, version in enumerate(card.version_history):
            assert version.version == i + 1

        # Current version should be 6
        assert card.version == 6


class TestCardWithVersioning:
    """Test Card model with versioning fields."""

    def test_card_has_versioning_fields(self):
        """Test that Card has all versioning fields."""
        card = create_test_card()

        assert hasattr(card, "version")
        assert hasattr(card, "version_history")
        assert hasattr(card, "created_at")
        assert hasattr(card, "updated_at")

    def test_card_serialization_includes_versions(self):
        """Test that versioning is included in serialization."""
        card = create_test_card()
        card.save_version("Test save")

        data = card.model_dump()

        assert "version" in data
        assert "version_history" in data
        assert len(data["version_history"]) == 1

    def test_card_from_dict_with_versions(self):
        """Test loading card with version history from dict."""
        data = {
            "id": "test-1",
            "format": "qa",
            "card_type": "concept",
            "question": "Q?",
            "answer": "A",
            "importance": 5,
            "difficulty": 5,
            "source_chapter": "Ch1",
            "source_chapter_index": 0,
            "version": 3,
            "version_history": [
                {"version": 1, "question": "Original Q?", "timestamp": "2024-01-01T00:00:00"},
                {"version": 2, "question": "Updated Q?", "timestamp": "2024-01-02T00:00:00"},
            ],
        }

        card = Card(**data)

        assert card.version == 3
        assert len(card.version_history) == 2
        assert card.version_history[0].question == "Original Q?"
