"""Tests for data models."""


from epub_to_anki.models import (
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    Density,
)


def test_card_qa_creation():
    """Test creating a Q&A card."""
    card = Card(
        id="test123",
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question="What is photosynthesis?",
        answer="The process by which plants convert sunlight into energy",
        importance=8,
        difficulty=5,
        source_chapter="Chapter 1",
        source_chapter_index=0,
    )

    assert card.format == CardFormat.QA
    assert card.question == "What is photosynthesis?"
    assert card.compute_score() == (8 * 2 + 5) / 3  # 7.0


def test_card_cloze_creation():
    """Test creating a Cloze card."""
    card = Card(
        id="test456",
        format=CardFormat.CLOZE,
        card_type=CardType.TERM,
        cloze_text="{{c1::Photosynthesis}} is the process plants use to convert sunlight.",
        importance=7,
        difficulty=4,
        source_chapter="Chapter 1",
        source_chapter_index=0,
    )

    assert card.format == CardFormat.CLOZE
    assert "{{c1::" in card.cloze_text


def test_card_display_text():
    """Test card display text generation."""
    qa_card = Card(
        id="test1",
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question="Q?",
        answer="A",
        importance=5,
        difficulty=5,
        source_chapter="Ch1",
        source_chapter_index=0,
    )

    cloze_card = Card(
        id="test2",
        format=CardFormat.CLOZE,
        card_type=CardType.TERM,
        cloze_text="{{c1::test}}",
        importance=5,
        difficulty=5,
        source_chapter="Ch1",
        source_chapter_index=0,
    )

    assert "Q: Q?" in qa_card.get_display_text()
    assert "A: A" in qa_card.get_display_text()
    assert "Cloze: {{c1::test}}" in cloze_card.get_display_text()


def test_chapter_cards_filtering():
    """Test ChapterCards included/excluded filtering."""
    chapter = Chapter(
        index=0,
        title="Test Chapter",
        content="Test content",
        word_count=100,
    )

    cards = [
        Card(
            id="1",
            format=CardFormat.QA,
            card_type=CardType.CONCEPT,
            question="Q1",
            answer="A1",
            importance=8,
            difficulty=5,
            source_chapter="Test",
            source_chapter_index=0,
            status=CardStatus.INCLUDED,
        ),
        Card(
            id="2",
            format=CardFormat.QA,
            card_type=CardType.CONCEPT,
            question="Q2",
            answer="A2",
            importance=3,
            difficulty=3,
            source_chapter="Test",
            source_chapter_index=0,
            status=CardStatus.EXCLUDED,
        ),
    ]

    cc = ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)

    assert len(cc.included_cards) == 1
    assert len(cc.excluded_cards) == 1
    assert cc.included_cards[0].id == "1"
    assert cc.excluded_cards[0].id == "2"


def test_card_score_calculation():
    """Test card score calculation."""
    # Score = (importance * 2 + difficulty) / 3
    card = Card(
        id="test",
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question="Q",
        answer="A",
        importance=9,
        difficulty=6,
        source_chapter="Test",
        source_chapter_index=0,
    )

    expected_score = (9 * 2 + 6) / 3  # 8.0
    assert card.compute_score() == expected_score
