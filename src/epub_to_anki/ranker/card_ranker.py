"""Rank and filter cards based on importance/difficulty scores."""

from ..models import Card, CardStatus, ChapterCards, Density


def compute_card_score(card: Card) -> float:
    """
    Compute overall score for a card.

    Higher score = more likely to include.
    Weights importance more heavily than difficulty.
    """
    return (card.importance * 2 + card.difficulty) / 3


def get_default_threshold(density: Density) -> float:
    """Get default score threshold for a density setting."""
    thresholds = {
        Density.LIGHT: 7.0,  # Only high-importance cards
        Density.MEDIUM: 5.0,  # Moderate threshold
        Density.THOROUGH: 3.0,  # Include most cards
    }
    return thresholds[density]


def rank_cards(cards: list[Card]) -> list[Card]:
    """
    Sort cards by score (highest first).

    Args:
        cards: List of cards to rank

    Returns:
        Cards sorted by score descending
    """
    return sorted(cards, key=compute_card_score, reverse=True)


def apply_threshold(
    cards: list[Card],
    threshold: float,
) -> list[Card]:
    """
    Apply a score threshold to cards.

    Cards at or above threshold get status INCLUDED.
    Cards below threshold get status EXCLUDED.

    Args:
        cards: List of cards to filter
        threshold: Minimum score to include

    Returns:
        The same cards with updated status
    """
    for card in cards:
        score = compute_card_score(card)
        if score >= threshold:
            card.status = CardStatus.INCLUDED
        else:
            card.status = CardStatus.EXCLUDED
    return cards


def apply_top_n(cards: list[Card], n: int) -> list[Card]:
    """
    Include only the top N cards by score.

    Args:
        cards: List of cards to filter
        n: Number of cards to include

    Returns:
        The same cards with updated status
    """
    ranked = rank_cards(cards)
    for i, card in enumerate(ranked):
        if i < n:
            card.status = CardStatus.INCLUDED
        else:
            card.status = CardStatus.EXCLUDED
    return cards


class CardRanker:
    """Handles ranking and filtering of cards within chapters."""

    def __init__(self, default_density: Density = Density.MEDIUM):
        self.default_density = default_density

    def rank_chapter(self, chapter_cards: ChapterCards) -> ChapterCards:
        """
        Rank all cards in a chapter by score.

        Args:
            chapter_cards: ChapterCards to rank

        Returns:
            Same ChapterCards with cards sorted by score
        """
        chapter_cards.cards = rank_cards(chapter_cards.cards)
        return chapter_cards

    def apply_density_threshold(
        self,
        chapter_cards: ChapterCards,
        density: Density | None = None,
    ) -> ChapterCards:
        """
        Apply density-based threshold to a chapter's cards.

        Args:
            chapter_cards: ChapterCards to filter
            density: Density setting (uses chapter's density_used if not specified)

        Returns:
            Same ChapterCards with updated card statuses
        """
        density = density or chapter_cards.density_used
        threshold = get_default_threshold(density)
        chapter_cards.threshold = threshold
        chapter_cards.cards = apply_threshold(chapter_cards.cards, threshold)
        return chapter_cards

    def apply_custom_threshold(
        self,
        chapter_cards: ChapterCards,
        threshold: float,
    ) -> ChapterCards:
        """
        Apply a custom score threshold to a chapter's cards.

        Args:
            chapter_cards: ChapterCards to filter
            threshold: Minimum score to include (1-10 scale)

        Returns:
            Same ChapterCards with updated card statuses
        """
        chapter_cards.threshold = threshold
        chapter_cards.cards = apply_threshold(chapter_cards.cards, threshold)
        return chapter_cards

    def apply_card_limit(
        self,
        chapter_cards: ChapterCards,
        max_cards: int,
    ) -> ChapterCards:
        """
        Limit chapter to top N cards.

        Args:
            chapter_cards: ChapterCards to filter
            max_cards: Maximum cards to include

        Returns:
            Same ChapterCards with updated card statuses
        """
        chapter_cards.cards = apply_top_n(chapter_cards.cards, max_cards)
        return chapter_cards

    def get_score_distribution(self, chapter_cards: ChapterCards) -> dict:
        """
        Get statistics about card score distribution.

        Returns dict with min, max, mean, median, and counts by score bucket.
        """
        if not chapter_cards.cards:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "buckets": {}, "total": 0}

        scores = [compute_card_score(c) for c in chapter_cards.cards]
        scores.sort()

        # Score buckets: 1-3, 4-5, 6-7, 8-10
        buckets = {
            "1-3 (low)": len([s for s in scores if s < 4]),
            "4-5 (medium)": len([s for s in scores if 4 <= s < 6]),
            "6-7 (high)": len([s for s in scores if 6 <= s < 8]),
            "8-10 (critical)": len([s for s in scores if s >= 8]),
        }

        # Calculate median correctly for both odd and even length lists
        n = len(scores)
        if n % 2 == 1:
            median = scores[n // 2]
        else:
            median = (scores[n // 2 - 1] + scores[n // 2]) / 2

        return {
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
            "mean": round(sum(scores) / len(scores), 1),
            "median": round(median, 1),
            "total": len(scores),
            "buckets": buckets,
        }

    def preview_threshold(
        self,
        chapter_cards: ChapterCards,
        threshold: float,
    ) -> dict:
        """
        Preview what a threshold would do without applying it.

        Returns:
            Dict with counts of what would be included/excluded
        """
        included = 0
        excluded = 0

        for card in chapter_cards.cards:
            score = compute_card_score(card)
            if score >= threshold:
                included += 1
            else:
                excluded += 1

        return {
            "threshold": threshold,
            "would_include": included,
            "would_exclude": excluded,
            "total": len(chapter_cards.cards),
        }
