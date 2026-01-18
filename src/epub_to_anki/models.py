"""Data models for the EPUB to Anki pipeline."""

from datetime import datetime
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


class ImageRef(BaseModel):
    """Reference to an extracted image."""

    id: str = Field(description="Unique identifier for this image")
    filename: str = Field(description="Original filename in EPUB")
    media_type: str = Field(description="MIME type (e.g., image/png)")
    chapter_index: Optional[int] = Field(default=None, description="Chapter where image appears")
    width: Optional[int] = Field(default=None, description="Image width in pixels")
    height: Optional[int] = Field(default=None, description="Image height in pixels")
    # Note: Binary data stored separately, not in JSON


class CardVersion(BaseModel):
    """A version entry for card history tracking."""

    version: int = Field(description="Version number (1, 2, 3...)")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    question: Optional[str] = Field(default=None)
    answer: Optional[str] = Field(default=None)
    cloze_text: Optional[str] = Field(default=None)
    importance: Optional[int] = Field(default=None)
    difficulty: Optional[int] = Field(default=None)
    change_reason: Optional[str] = Field(default=None, description="Why this change was made")


class Chapter(BaseModel):
    """A chapter extracted from an EPUB."""

    index: int = Field(description="Chapter number (0-indexed)")
    title: str = Field(description="Chapter title")
    content: str = Field(description="Plain text content of the chapter")
    word_count: int = Field(description="Number of words in the chapter")
    html_content: Optional[str] = Field(default=None, description="Original HTML if preserved")
    image_ids: list[str] = Field(default_factory=list, description="IDs of images in this chapter")


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

    # Image reference (for cards with images)
    image_id: Optional[str] = Field(default=None, description="Reference to an image")

    # Status
    status: CardStatus = Field(default=CardStatus.INCLUDED)
    tags: list[str] = Field(default_factory=list)

    # Reverse card option (for QA cards)
    generate_reverse: bool = Field(default=False, description="Generate Answer→Question reverse card")

    # Versioning
    version: int = Field(default=1, description="Current version number")
    version_history: list[CardVersion] = Field(default_factory=list, description="Previous versions")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

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

    def save_version(self, change_reason: Optional[str] = None) -> None:
        """Save current state to version history before making changes."""
        version_entry = CardVersion(
            version=self.version,
            question=self.question,
            answer=self.answer,
            cloze_text=self.cloze_text,
            importance=self.importance,
            difficulty=self.difficulty,
            change_reason=change_reason,
        )
        self.version_history.append(version_entry)
        self.version += 1
        self.updated_at = datetime.now().isoformat()


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
    images: list[ImageRef] = Field(default_factory=list, description="All images in the book")

    @property
    def total_words(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    def get_image(self, image_id: str) -> Optional[ImageRef]:
        """Get an image by ID."""
        for img in self.images:
            if img.id == image_id:
                return img
        return None


class CardTemplate(BaseModel):
    """Custom card template configuration."""

    name: str = Field(description="Template name")
    front_html: str = Field(description="Front template HTML")
    back_html: str = Field(description="Back template HTML")
    css: str = Field(default="", description="Custom CSS styling")


class DeckConfig(BaseModel):
    """Configuration for deck export."""

    parent_deck: Optional[str] = Field(default=None, description="Parent deck name for hierarchical decks")
    use_chapter_subdecks: bool = Field(default=False, description="Create subdecks per chapter")
    include_reverse_cards: bool = Field(default=False, description="Generate reverse QA cards")
    custom_qa_template: Optional[CardTemplate] = Field(default=None, description="Custom QA card template")
    custom_cloze_template: Optional[CardTemplate] = Field(default=None, description="Custom Cloze template")
    custom_css: Optional[str] = Field(default=None, description="Override default CSS")


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
    chapter_densities: dict[int, Density] = Field(
        default_factory=dict,
        description="Per-chapter density overrides (chapter_index -> density)"
    )
    extract_images: bool = Field(default=False, description="Extract and include images from EPUB")


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
