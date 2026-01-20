"""Duplicate detection and handling for flashcards."""

import re
from dataclasses import dataclass, field

from .models import Card, CardFormat, CardStatus, ChapterCards


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    # Lowercase
    text = text.lower()
    # Remove cloze markers
    text = re.sub(r"\{\{c\d+::(.*?)\}\}", r"\1", text)
    # Remove punctuation
    text = re.sub(r"[^\w\s]", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_card_text(card: Card) -> str:
    """Get the main text content of a card for comparison."""
    if card.format == CardFormat.QA:
        return f"{card.question or ''} {card.answer or ''}"
    else:
        return card.cloze_text or ""


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # j+1 instead of j since previous_row and current_row are one character longer
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def similarity_ratio(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings.

    Returns a value between 0 (completely different) and 1 (identical).
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return 1 - (distance / max_len)


@dataclass
class DuplicateGroup:
    """A group of duplicate or similar cards."""

    primary_card: Card
    duplicates: list[Card] = field(default_factory=list)
    similarity_scores: list[float] = field(default_factory=list)

    @property
    def all_cards(self) -> list[Card]:
        """Get all cards in this group."""
        return [self.primary_card] + self.duplicates

    @property
    def count(self) -> int:
        """Total number of cards in this group."""
        return 1 + len(self.duplicates)


@dataclass
class DeduplicationResult:
    """Result of duplicate detection."""

    total_cards: int
    unique_cards: int
    duplicate_groups: list[DuplicateGroup]
    exact_duplicates: int
    similar_duplicates: int

    @property
    def duplicates_found(self) -> int:
        """Total duplicates found."""
        return sum(g.count - 1 for g in self.duplicate_groups)

    def __str__(self) -> str:
        return (
            f"Deduplication Results:\n"
            f"  Total cards: {self.total_cards}\n"
            f"  Unique cards: {self.unique_cards}\n"
            f"  Duplicates found: {self.duplicates_found}\n"
            f"    Exact: {self.exact_duplicates}\n"
            f"    Similar: {self.similar_duplicates}"
        )


class CardDeduplicator:
    """Detect and handle duplicate cards."""

    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Minimum similarity ratio to consider as duplicate (0-1)
        """
        self.similarity_threshold = similarity_threshold

    def find_duplicates(
        self,
        cards: list[Card],
        cross_chapter: bool = True,
    ) -> DeduplicationResult:
        """
        Find duplicate cards in a list.

        Args:
            cards: List of cards to check
            cross_chapter: If True, check across chapters; if False, only within same chapter

        Returns:
            DeduplicationResult with duplicate groups
        """
        if not cards:
            return DeduplicationResult(
                total_cards=0,
                unique_cards=0,
                duplicate_groups=[],
                exact_duplicates=0,
                similar_duplicates=0,
            )

        # Normalize all card texts
        normalized_cards = [
            (card, normalize_text(get_card_text(card))) for card in cards
        ]

        # Track which cards have been assigned to a group
        assigned: set[str] = set()
        duplicate_groups: list[DuplicateGroup] = []
        exact_count = 0
        similar_count = 0

        for i, (card1, text1) in enumerate(normalized_cards):
            if card1.id in assigned:
                continue

            # Start a new potential group
            group = DuplicateGroup(primary_card=card1)
            assigned.add(card1.id)

            for j, (card2, text2) in enumerate(normalized_cards[i + 1 :], start=i + 1):
                if card2.id in assigned:
                    continue

                # Skip if not cross_chapter and different chapters
                if not cross_chapter and card1.source_chapter_index != card2.source_chapter_index:
                    continue

                # Check for exact match first
                if text1 == text2:
                    group.duplicates.append(card2)
                    group.similarity_scores.append(1.0)
                    assigned.add(card2.id)
                    exact_count += 1
                else:
                    # Check similarity
                    sim = similarity_ratio(text1, text2)
                    if sim >= self.similarity_threshold:
                        group.duplicates.append(card2)
                        group.similarity_scores.append(sim)
                        assigned.add(card2.id)
                        similar_count += 1

            # Only add group if it has duplicates
            if group.duplicates:
                duplicate_groups.append(group)

        return DeduplicationResult(
            total_cards=len(cards),
            unique_cards=len(cards) - exact_count - similar_count,
            duplicate_groups=duplicate_groups,
            exact_duplicates=exact_count,
            similar_duplicates=similar_count,
        )

    def find_duplicates_in_chapters(
        self,
        chapter_cards_list: list[ChapterCards],
    ) -> DeduplicationResult:
        """
        Find duplicates across multiple chapters.

        Args:
            chapter_cards_list: List of ChapterCards to check

        Returns:
            DeduplicationResult with duplicate groups
        """
        all_cards = []
        for cc in chapter_cards_list:
            all_cards.extend(cc.cards)
        return self.find_duplicates(all_cards, cross_chapter=True)

    def mark_duplicates_excluded(
        self,
        result: DeduplicationResult,
        keep_strategy: str = "highest_score",
    ) -> int:
        """
        Mark duplicate cards as excluded, keeping one from each group.

        Args:
            result: DeduplicationResult from find_duplicates
            keep_strategy: How to choose which card to keep:
                - "highest_score": Keep the card with highest computed score
                - "first": Keep the first card (primary)
                - "highest_importance": Keep the card with highest importance

        Returns:
            Number of cards marked as excluded
        """
        excluded_count = 0

        for group in result.duplicate_groups:
            if keep_strategy == "first":
                # Keep primary, exclude all duplicates
                for card in group.duplicates:
                    card.status = CardStatus.EXCLUDED
                    excluded_count += 1
            elif keep_strategy == "highest_score":
                # Find card with highest score
                all_cards = group.all_cards
                best_card = max(all_cards, key=lambda c: c.compute_score())
                for card in all_cards:
                    if card.id != best_card.id:
                        card.status = CardStatus.EXCLUDED
                        excluded_count += 1
            elif keep_strategy == "highest_importance":
                # Find card with highest importance
                all_cards = group.all_cards
                best_card = max(all_cards, key=lambda c: c.importance)
                for card in all_cards:
                    if card.id != best_card.id:
                        card.status = CardStatus.EXCLUDED
                        excluded_count += 1

        return excluded_count

    def get_duplicate_summary(
        self,
        result: DeduplicationResult,
        max_examples: int = 3,
    ) -> str:
        """
        Get a human-readable summary of duplicates found.

        Args:
            result: DeduplicationResult to summarize
            max_examples: Maximum example groups to show

        Returns:
            Formatted summary string
        """
        lines = [
            "Duplicate Detection Summary",
            "─" * 40,
            f"Total cards analyzed: {result.total_cards}",
            f"Unique cards: {result.unique_cards}",
            f"Duplicate groups: {len(result.duplicate_groups)}",
            f"  Exact matches: {result.exact_duplicates}",
            f"  Similar cards: {result.similar_duplicates}",
        ]

        if result.duplicate_groups and max_examples > 0:
            lines.append("")
            num_shown = min(max_examples, len(result.duplicate_groups))
            lines.append(f"Example duplicates (showing {num_shown}):")

            for i, group in enumerate(result.duplicate_groups[:max_examples]):
                lines.append(f"\n  Group {i + 1} ({group.count} cards):")
                primary_text = get_card_text(group.primary_card)[:60]
                lines.append(f"    Primary: {primary_text}...")

                for j, (dup, sim) in enumerate(
                    zip(group.duplicates[:2], group.similarity_scores[:2])
                ):
                    dup_text = get_card_text(dup)[:60]
                    lines.append(f"    Similar ({sim:.0%}): {dup_text}...")

                if len(group.duplicates) > 2:
                    lines.append(f"    ... and {len(group.duplicates) - 2} more")

        return "\n".join(lines)
