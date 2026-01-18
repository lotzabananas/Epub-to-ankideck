"""Data models for the EPUB to Anki pipeline."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CardFormat(str, Enum):
    """The format of a flashcard."""

    QA = "qa"
    CLOZE = "cloze"


class CardType(str, Enum):
    """The semantic type of card content."""

    CONCEPT = "concept"
    FACT = "fact"
    PROCESS = "process"
    TERM = "term"
    RELATIONSHIP = "relationship"
    EXAMPLE = "example"


class CardStatus(str, Enum):
    """Whether a card made the cut."""

    INCLUDED = "included"
    EXCLUDED = "excluded"


class Density(str, Enum):
    """Card generation density setting."""

    LIGHT = "light"  # Core concepts only (~1 card per 2-3 pages)
    MEDIUM = "medium"  # Key ideas + supporting facts (~1 card per page)
    THOROUGH = "thorough"  # Comprehensive coverage (~2-3 cards per page)


class Chapter(BaseModel):
    """A chapter extracted from an EPUB."""

    index: int = Field(description="Chapter number (0-indexed)")
    title: str = Field(description="Chapter title")
    content: str = Field(description="Plain text content of the chapter")
    word_count: int = Field(description="Number of words in the chapter")
    html_content: Optional[str] = Field(default=None, description="Original HTML if preserved")


class Card(BaseModel):
    """A single flashcard."""

    id: str = Field(description="Unique identifier for this card")
    format: CardFormat = Field(description="QA or Cloze")
    card_type: CardType = Field(description="Semantic type of the content")

    # Content - for QA cards
    question: Optional[str] = Field(default=None, description="Question (for QA format)")
    answer: Optional[str] = Field(default=None, description="Answer (for QA format)")

    # Content - for Cloze cards
    cloze_text: Optional[str] = Field(default=None, description="Cloze text with {{c1::...}} markup")

    # Ranking
    importance: int = Field(ge=1, le=10, description="How essential is this knowledge (1-10)")
    difficulty: int = Field(ge=1, le=10, description="How hard to remember (1-10)")

    # Metadata (hidden on card, stored for reference)
    source_chapter: str = Field(description="Chapter title")
    source_chapter_index: int = Field(description="Chapter number")
    source_section: Optional[str] = Field(default=None, description="Section heading if available")
    source_quote: Optional[str] = Field(default=None, description="Original text this card is based on")

    # Status
    status: CardStatus = Field(default=CardStatus.INCLUDED)
    tags: list[str] = Field(default_factory=list)

    def get_display_text(self) -> str:
        """Get human-readable card content."""
        if self.format == CardFormat.QA:
            return f"Q: {self.question}\nA: {self.answer}"
        else:
            return f"Cloze: {self.cloze_text}"

    def compute_score(self) -> float:
        """Compute overall score for ranking. Higher = more likely to include."""
        # Weight importance more heavily than difficulty
        return (self.importance * 2 + self.difficulty) / 3


class ChapterCards(BaseModel):
    """All cards generated from a single chapter."""

    chapter: Chapter
    cards: list[Card] = Field(default_factory=list)
    density_used: Density = Field(description="Density setting used for generation")
    threshold: Optional[float] = Field(default=None, description="Score threshold used for filtering")

    @property
    def included_cards(self) -> list[Card]:
        """Cards that made the cut."""
        return [c for c in self.cards if c.status == CardStatus.INCLUDED]

    @property
    def excluded_cards(self) -> list[Card]:
        """Cards below the threshold."""
        return [c for c in self.cards if c.status == CardStatus.EXCLUDED]


class Book(BaseModel):
    """A parsed EPUB book."""

    title: str
    author: str
    chapters: list[Chapter] = Field(default_factory=list)
    language: Optional[str] = Field(default=None)
    identifier: Optional[str] = Field(default=None, description="ISBN or other identifier")

    @property
    def total_words(self) -> int:
        return sum(ch.word_count for ch in self.chapters)


class ProcessingConfig(BaseModel):
    """Configuration for the card generation pipeline."""

    density: Density = Field(default=Density.MEDIUM)
    auto_threshold: bool = Field(
        default=False, description="Automatically apply threshold without manual review"
    )
    importance_threshold: int = Field(
        default=5, ge=1, le=10, description="Minimum importance score to include (when auto)"
    )
    include_cloze: bool = Field(default=True, description="Generate cloze cards")
    include_qa: bool = Field(default=True, description="Generate Q&A cards")
    chapters_to_process: Optional[list[int]] = Field(
        default=None, description="Specific chapter indices to process (None = all)"
    )


class DeckMetadata(BaseModel):
    """Metadata about the generated deck."""

    book_title: str
    book_author: str
    total_cards: int
    included_cards: int
    excluded_cards: int
    chapters_processed: int
    density_used: Density
    config: ProcessingConfig
