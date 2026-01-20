"""Cost estimation for Claude API calls."""

from dataclasses import dataclass
from typing import Optional

from .models import Book, Chapter, Density


@dataclass
class CostEstimate:
    """Estimated cost for processing."""

    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    chapters_count: int
    total_words: int
    density: str

    # Per-chapter breakdown
    chapter_estimates: list[dict]

    def __str__(self) -> str:
        return (
            f"Estimated cost: ${self.estimated_cost_usd:.4f} USD\n"
            f"  Input tokens: ~{self.total_input_tokens:,}\n"
            f"  Output tokens: ~{self.total_output_tokens:,}\n"
            f"  Chapters: {self.chapters_count}\n"
            f"  Total words: {self.total_words:,}"
        )


class CostEstimator:
    """Estimate API costs before generation."""

    # Claude Sonnet 4 pricing (as of 2024)
    # https://www.anthropic.com/pricing
    INPUT_PRICE_PER_1M = 3.00  # $3 per 1M input tokens
    OUTPUT_PRICE_PER_1M = 15.00  # $15 per 1M output tokens

    # Estimation ratios
    CHARS_PER_TOKEN = 4  # Rough estimate for English text
    SYSTEM_PROMPT_TOKENS = 1500  # Approximate system prompt size
    PROMPT_TEMPLATE_TOKENS = 500  # Template overhead per chapter

    # Expected output tokens per card
    TOKENS_PER_CARD = 150  # Average card JSON size

    # Cards per word ratios by density
    CARDS_PER_1000_WORDS = {
        Density.LIGHT: 2,  # ~1 card per 500 words
        Density.MEDIUM: 4,  # ~1 card per 250 words
        Density.THOROUGH: 8,  # ~1 card per 125 words
    }

    def __init__(
        self,
        input_price_per_1m: Optional[float] = None,
        output_price_per_1m: Optional[float] = None,
    ):
        """
        Initialize cost estimator.

        Args:
            input_price_per_1m: Override input token price per 1M tokens
            output_price_per_1m: Override output token price per 1M tokens
        """
        self.input_price = input_price_per_1m or self.INPUT_PRICE_PER_1M
        self.output_price = output_price_per_1m or self.OUTPUT_PRICE_PER_1M

    def estimate_chapter_tokens(
        self,
        chapter: Chapter,
        density: Density,
    ) -> dict:
        """
        Estimate tokens for a single chapter.

        Args:
            chapter: Chapter to estimate
            density: Generation density

        Returns:
            Dict with token estimates
        """
        # Input tokens: content + system prompt + template
        content_tokens = len(chapter.content) // self.CHARS_PER_TOKEN
        input_tokens = content_tokens + self.SYSTEM_PROMPT_TOKENS + self.PROMPT_TEMPLATE_TOKENS

        # Output tokens: estimated cards * tokens per card
        cards_per_1000 = self.CARDS_PER_1000_WORDS[density]
        estimated_cards = max(1, (chapter.word_count * cards_per_1000) // 1000)
        output_tokens = estimated_cards * self.TOKENS_PER_CARD

        return {
            "chapter_index": chapter.index,
            "chapter_title": chapter.title,
            "word_count": chapter.word_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cards": estimated_cards,
        }

    def estimate_book(
        self,
        book: Book,
        density: Density,
        chapter_indices: Optional[list[int]] = None,
    ) -> CostEstimate:
        """
        Estimate total cost for processing a book.

        Args:
            book: Book to estimate
            density: Generation density
            chapter_indices: Specific chapters to estimate (None = all)

        Returns:
            CostEstimate with full breakdown
        """
        chapters = book.chapters
        if chapter_indices:
            chapters = [ch for ch in chapters if ch.index in chapter_indices]

        chapter_estimates = []
        total_input = 0
        total_output = 0
        total_words = 0

        for chapter in chapters:
            estimate = self.estimate_chapter_tokens(chapter, density)
            chapter_estimates.append(estimate)
            total_input += estimate["input_tokens"]
            total_output += estimate["output_tokens"]
            total_words += chapter.word_count

        # Calculate cost
        input_cost = (total_input / 1_000_000) * self.input_price
        output_cost = (total_output / 1_000_000) * self.output_price
        total_cost = input_cost + output_cost

        return CostEstimate(
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            estimated_cost_usd=round(total_cost, 4),
            chapters_count=len(chapters),
            total_words=total_words,
            density=density.value,
            chapter_estimates=chapter_estimates,
        )

    def estimate_remaining(
        self,
        book: Book,
        density: Density,
        processed_indices: list[int],
    ) -> CostEstimate:
        """
        Estimate cost for remaining chapters (for resume scenarios).

        Args:
            book: Book being processed
            density: Generation density
            processed_indices: Already processed chapter indices

        Returns:
            CostEstimate for remaining chapters
        """
        remaining_indices = [
            ch.index for ch in book.chapters if ch.index not in processed_indices
        ]
        return self.estimate_book(book, density, remaining_indices)

    def format_estimate(self, estimate: CostEstimate, verbose: bool = False) -> str:
        """
        Format estimate for display.

        Args:
            estimate: CostEstimate to format
            verbose: Include per-chapter breakdown

        Returns:
            Formatted string
        """
        lines = [
            f"Cost Estimate ({estimate.density} density)",
            f"{'─' * 40}",
            f"Chapters to process: {estimate.chapters_count}",
            f"Total words: {estimate.total_words:,}",
            "",
            "Token estimates:",
            f"  Input:  ~{estimate.total_input_tokens:,} tokens",
            f"  Output: ~{estimate.total_output_tokens:,} tokens",
            "",
            f"Estimated cost: ${estimate.estimated_cost_usd:.4f} USD",
        ]

        if verbose and estimate.chapter_estimates:
            lines.append("")
            lines.append("Per-chapter breakdown:")
            for ch in estimate.chapter_estimates:
                lines.append(
                    f"  Ch {ch['chapter_index'] + 1}: {ch['chapter_title'][:30]}... "
                    f"(~{ch['estimated_cards']} cards)"
                )

        return "\n".join(lines)
