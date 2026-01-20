"""Tests for duplicate detection."""


from epub_to_anki.deduplicator import (
    CardDeduplicator,
    DeduplicationResult,
    levenshtein_distance,
    normalize_text,
    similarity_ratio,
)
from epub_to_anki.models import Card, CardFormat, CardStatus, CardType


def create_test_card(
    id: str,
    question: str,
    answer: str,
    chapter_index: int = 0,
) -> Card:
    """Helper to create test cards."""
    return Card(
        id=id,
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question=question,
        answer=answer,
        importance=5,
        difficulty=5,
        source_chapter=f"Chapter {chapter_index + 1}",
        source_chapter_index=chapter_index,
        status=CardStatus.INCLUDED,
    )


def test_normalize_text():
    """Test text normalization."""
    assert normalize_text("Hello World!") == "hello world"
    assert normalize_text("  Multiple   Spaces  ") == "multiple spaces"
    assert normalize_text("{{c1::cloze}}") == "cloze"


def test_levenshtein_distance():
    """Test Levenshtein distance calculation."""
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("abc", "abd") == 1
    assert levenshtein_distance("abc", "abcd") == 1
    assert levenshtein_distance("kitten", "sitting") == 3


def test_similarity_ratio():
    """Test similarity ratio calculation."""
    assert similarity_ratio("", "") == 1.0
    assert similarity_ratio("abc", "abc") == 1.0
    assert similarity_ratio("abc", "") == 0.0
    assert 0 < similarity_ratio("hello", "hallo") < 1


def test_find_exact_duplicates():
    """Test finding exact duplicate cards."""
    cards = [
        create_test_card("1", "What is X?", "X is Y"),
        create_test_card("2", "What is X?", "X is Y"),  # Exact duplicate
        create_test_card("3", "What is Z?", "Z is W"),
    ]

    deduplicator = CardDeduplicator()
    result = deduplicator.find_duplicates(cards)

    assert result.exact_duplicates == 1
    assert result.duplicates_found == 1
    assert len(result.duplicate_groups) == 1


def test_find_similar_duplicates():
    """Test finding similar (not exact) duplicates."""
    cards = [
        create_test_card("1", "What is photosynthesis?", "Converting light to energy"),
        create_test_card("2", "What is photosynthesis?", "The conversion of light to energy"),
        create_test_card("3", "What is gravity?", "A fundamental force"),
    ]

    deduplicator = CardDeduplicator(similarity_threshold=0.7)
    result = deduplicator.find_duplicates(cards)

    assert result.similar_duplicates >= 1 or result.exact_duplicates >= 1
    assert len(result.duplicate_groups) == 1


def test_no_duplicates():
    """Test when there are no duplicates."""
    cards = [
        create_test_card(
            "1", "What is photosynthesis?", "Plants converting light to energy"
        ),
        create_test_card(
            "2", "Define the theory of relativity",
            "Einstein's theory about space and time"
        ),
        create_test_card(
            "3", "Explain the water cycle",
            "Evaporation precipitation and collection"
        ),
    ]

    deduplicator = CardDeduplicator()
    result = deduplicator.find_duplicates(cards)

    assert result.duplicates_found == 0
    assert len(result.duplicate_groups) == 0


def test_cross_chapter_duplicates():
    """Test finding duplicates across chapters."""
    cards = [
        create_test_card("1", "What is X?", "Answer", chapter_index=0),
        create_test_card("2", "What is X?", "Answer", chapter_index=1),  # Same, different chapter
    ]

    deduplicator = CardDeduplicator()

    # With cross_chapter=True
    result_cross = deduplicator.find_duplicates(cards, cross_chapter=True)
    assert result_cross.duplicates_found == 1

    # With cross_chapter=False
    result_no_cross = deduplicator.find_duplicates(cards, cross_chapter=False)
    assert result_no_cross.duplicates_found == 0


def test_mark_duplicates_excluded_highest_score():
    """Test marking duplicates as excluded with highest_score strategy."""
    cards = [
        Card(
            id="1",
            format=CardFormat.QA,
            card_type=CardType.CONCEPT,
            question="What is X?",
            answer="Answer",
            importance=8,  # Higher score
            difficulty=5,
            source_chapter="Test",
            source_chapter_index=0,
        ),
        Card(
            id="2",
            format=CardFormat.QA,
            card_type=CardType.CONCEPT,
            question="What is X?",
            answer="Answer",
            importance=3,  # Lower score
            difficulty=3,
            source_chapter="Test",
            source_chapter_index=0,
        ),
    ]

    deduplicator = CardDeduplicator()
    result = deduplicator.find_duplicates(cards)
    excluded = deduplicator.mark_duplicates_excluded(result, "highest_score")

    assert excluded == 1
    # Card 1 (higher score) should be included, card 2 excluded
    assert cards[0].status == CardStatus.INCLUDED
    assert cards[1].status == CardStatus.EXCLUDED


def test_mark_duplicates_excluded_first():
    """Test marking duplicates as excluded with first strategy."""
    cards = [
        create_test_card("1", "What is X?", "Answer"),
        create_test_card("2", "What is X?", "Answer"),
    ]

    deduplicator = CardDeduplicator()
    result = deduplicator.find_duplicates(cards)
    excluded = deduplicator.mark_duplicates_excluded(result, "first")

    assert excluded == 1
    # First card should be kept
    assert cards[0].status == CardStatus.INCLUDED
    assert cards[1].status == CardStatus.EXCLUDED


def test_empty_cards_list():
    """Test with empty cards list."""
    deduplicator = CardDeduplicator()
    result = deduplicator.find_duplicates([])

    assert result.total_cards == 0
    assert result.duplicates_found == 0


def test_deduplication_result_str():
    """Test DeduplicationResult string representation."""
    result = DeduplicationResult(
        total_cards=10,
        unique_cards=8,
        duplicate_groups=[],
        exact_duplicates=1,
        similar_duplicates=1,
    )

    output = str(result)
    assert "10" in output
    assert "8" in output
