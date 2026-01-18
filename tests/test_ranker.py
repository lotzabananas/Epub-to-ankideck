"""Tests for card ranking and filtering."""

import pytest

from epub_to_anki.models import (
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    Density,
)
from epub_to_anki.ranker import CardRanker, apply_threshold, rank_cards


def create_test_card(id: str, importance: int, difficulty: int) -> Card:
    """Helper to create test cards."""
    return Card(
        id=id,
        format=CardFormat.QA,
        card_type=CardType.CONCEPT,
        question=f"Question {id}",
        answer=f"Answer {id}",
        importance=importance,
        difficulty=difficulty,
        source_chapter="Test",
        source_chapter_index=0,
    )


def test_rank_cards():
    """Test cards are ranked by score descending."""
    cards = [
        create_test_card("low", 3, 3),  # Score: 3.0
        create_test_card("high", 9, 9),  # Score: 9.0
        create_test_card("med", 6, 6),  # Score: 6.0
    ]

    ranked = rank_cards(cards)

    assert ranked[0].id == "high"
    assert ranked[1].id == "med"
    assert ranked[2].id == "low"


def test_apply_threshold():
    """Test threshold application."""
    cards = [
        create_test_card("high", 9, 6),  # Score: 8.0
        create_test_card("med", 6, 6),  # Score: 6.0
        create_test_card("low", 3, 3),  # Score: 3.0
    ]

    apply_threshold(cards, 5.0)

    high_card = next(c for c in cards if c.id == "high")
    med_card = next(c for c in cards if c.id == "med")
    low_card = next(c for c in cards if c.id == "low")

    assert high_card.status == CardStatus.INCLUDED
    assert med_card.status == CardStatus.INCLUDED
    assert low_card.status == CardStatus.EXCLUDED


def test_ranker_preview_threshold():
    """Test threshold preview."""
    chapter = Chapter(index=0, title="Test", content="", word_count=0)
    cards = [
        create_test_card("1", 9, 9),  # 9.0
        create_test_card("2", 7, 7),  # 7.0
        create_test_card("3", 5, 5),  # 5.0
        create_test_card("4", 3, 3),  # 3.0
    ]
    cc = ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)

    ranker = CardRanker()
    preview = ranker.preview_threshold(cc, 6.0)

    assert preview["would_include"] == 2  # Cards with score >= 6.0
    assert preview["would_exclude"] == 2


def test_ranker_score_distribution():
    """Test score distribution calculation."""
    chapter = Chapter(index=0, title="Test", content="", word_count=0)
    cards = [
        create_test_card("1", 9, 9),  # 9.0 - critical
        create_test_card("2", 7, 7),  # 7.0 - high
        create_test_card("3", 5, 5),  # 5.0 - medium
        create_test_card("4", 2, 2),  # 2.0 - low
    ]
    cc = ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)

    ranker = CardRanker()
    stats = ranker.get_score_distribution(cc)

    assert stats["total"] == 4
    assert stats["min"] == 2.0
    assert stats["max"] == 9.0
    assert stats["buckets"]["8-10 (critical)"] == 1
    assert stats["buckets"]["6-7 (high)"] == 1
    assert stats["buckets"]["4-5 (medium)"] == 1
    assert stats["buckets"]["1-3 (low)"] == 1
