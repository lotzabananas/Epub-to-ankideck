"""Data models for the EPUB to Anki pipeline."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CardFormat(str, Enum):
    """The format of a flashcard."""

    QA = "qa"
    CLOZE = "cloze"


class CardTemplate(BaseModel):
    """Custom HTML/CSS template for card rendering."""

    name: str = Field(description="Template name identifier")
    front_html: str = Field(description="HTML template for card front")
    back_html: str = Field(description="HTML template for card back")
    css: str = Field(description="CSS styling for the card")

    @classmethod
    def default_qa(cls) -> "CardTemplate":
        """Get the default Q&A template."""
        return cls(
            name="default_qa",
            front_html='<div class="question">{{Question}}</div>',
            back_html='''<div class="question">{{Question}}</div>
<hr id="answer">
<div class="answer">{{Answer}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>''',
            css="""
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 18px;
    text-align: left;
    color: #1a1a1a;
    background-color: #ffffff;
    padding: 20px;
    line-height: 1.5;
}

.question {
    font-size: 20px;
    margin-bottom: 20px;
}

.answer {
    border-top: 1px solid #e0e0e0;
    padding-top: 20px;
}

.metadata {
    font-size: 12px;
    color: #888;
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid #f0f0f0;
}

.source-chapter {
    font-style: italic;
}

.night_mode .card {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.night_mode .metadata {
    color: #666;
    border-top-color: #333;
}

.night_mode .answer {
    border-top-color: #333;
}
"""
        )

    @classmethod
    def default_cloze(cls) -> "CardTemplate":
        """Get the default Cloze template."""
        return cls(
            name="default_cloze",
            front_html='<div class="cloze-text">{{cloze:Text}}</div>',
            back_html='''<div class="cloze-text">{{cloze:Text}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>''',
            css="""
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 18px;
    text-align: left;
    color: #1a1a1a;
    background-color: #ffffff;
    padding: 20px;
    line-height: 1.5;
}

.cloze {
    font-weight: bold;
    color: #0066cc;
}

.metadata {
    font-size: 12px;
    color: #888;
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid #f0f0f0;
}

.source-chapter {
    font-style: italic;
}

.night_mode .card {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.night_mode .cloze {
    color: #66b3ff;
}

.night_mode .metadata {
    color: #666;
    border-top-color: #333;
}
"""
        )


class DeckConfig(BaseModel):
    """Configuration for deck generation and export."""

    deck_name: Optional[str] = Field(default=None, description="Custom deck name (defaults to book title)")
    parent_deck: Optional[str] = Field(default=None, description="Parent deck name for nesting")
    create_subdecks: bool = Field(default=False, description="Create per-chapter subdecks")
    include_reverse: bool = Field(default=False, description="Generate reverse (Answer→Question) cards")
    extract_images: bool = Field(default=False, description="Extract and embed images from EPUB")
    qa_template: Optional[CardTemplate] = Field(default=None, description="Custom Q&A template")
    cloze_template: Optional[CardTemplate] = Field(default=None, description="Custom Cloze template")

    def get_full_deck_name(self, book_title: str, book_author: str) -> str:
        """Get the full deck name including parent if specified."""
        base_name = self.deck_name or f"{book_title} - {book_author}"
        if self.parent_deck:
            return f"{self.parent_deck}::{base_name}"
        return base_name

    def get_chapter_deck_name(self, base_deck_name: str, chapter_title: str, chapter_index: int) -> str:
        """Get the subdeck name for a chapter."""
        if self.create_subdecks:
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in chapter_title)
            return f"{base_deck_name}::Ch{chapter_index + 1} - {safe_title}"
        return base_deck_name


class CardVersion(BaseModel):
    """A version snapshot of a card's content."""

    version: int = Field(description="Version number (1-indexed)")
    timestamp: datetime = Field(default_factory=datetime.now)
    question: Optional[str] = Field(default=None)
    answer: Optional[str] = Field(default=None)
    cloze_text: Optional[str] = Field(default=None)
    importance: int = Field(ge=1, le=10)
    difficulty: int = Field(ge=1, le=10)
    editor_note: Optional[str] = Field(default=None, description="Optional note about this edit")


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


class EpubImage(BaseModel):
    """An image extracted from an EPUB file."""

    id: str = Field(description="Unique identifier for the image")
    filename: str = Field(description="Original filename in EPUB")
    media_type: str = Field(description="MIME type (e.g., image/jpeg)")
    data: bytes = Field(description="Raw image data")
    source_chapter_index: Optional[int] = Field(default=None, description="Chapter this image appears in")

    class Config:
        arbitrary_types_allowed = True


class Chapter(BaseModel):
    """A chapter extracted from an EPUB."""

    index: int = Field(description="Chapter number (0-indexed)")
    title: str = Field(description="Chapter title")
    content: str = Field(description="Plain text content of the chapter")
    word_count: int = Field(description="Number of words in the chapter")
    html_content: Optional[str] = Field(default=None, description="Original HTML if preserved")
    images: list[EpubImage] = Field(default_factory=list, description="Images in this chapter")


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

    # Versioning
    created_at: datetime = Field(default_factory=datetime.now, description="When the card was created")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last modification time")
    version_history: list[CardVersion] = Field(default_factory=list, description="Edit history")

    # Reverse card tracking
    is_reverse: bool = Field(default=False, description="True if this is a reverse (A→Q) card")
    original_card_id: Optional[str] = Field(default=None, description="ID of original card if this is a reverse")

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

    def save_version(self, editor_note: Optional[str] = None) -> CardVersion:
        """
        Save the current state as a version before editing.

        Args:
            editor_note: Optional note about this version/edit

        Returns:
            The created CardVersion object
        """
        version = CardVersion(
            version=len(self.version_history) + 1,
            timestamp=datetime.now(),
            question=self.question,
            answer=self.answer,
            cloze_text=self.cloze_text,
            importance=self.importance,
            difficulty=self.difficulty,
            editor_note=editor_note,
        )
        self.version_history.append(version)
        self.updated_at = datetime.now()
        return version

    def restore_version(self, version_number: int) -> bool:
        """
        Restore card content from a previous version.

        Args:
            version_number: Version number to restore (1-indexed)

        Returns:
            True if successful, False if version not found
        """
        if version_number < 1 or version_number > len(self.version_history):
            return False

        version = self.version_history[version_number - 1]

        # Save current state before restoring
        self.save_version(f"Before restoring to v{version_number}")

        # Restore content
        if self.format == CardFormat.QA:
            self.question = version.question
            self.answer = version.answer
        else:
            self.cloze_text = version.cloze_text

        self.importance = version.importance
        self.difficulty = version.difficulty
        self.updated_at = datetime.now()

        return True

    def create_reverse(self) -> Optional["Card"]:
        """
        Create a reverse card (Answer→Question) from this Q&A card.

        Returns:
            New Card with question and answer swapped, or None if not a Q&A card
        """
        if self.format != CardFormat.QA or not self.question or not self.answer:
            return None

        import uuid
        reverse_id = f"{self.id}_rev"

        return Card(
            id=reverse_id,
            format=CardFormat.QA,
            card_type=self.card_type,
            question=self.answer,  # Swap Q&A
            answer=self.question,
            importance=self.importance,
            difficulty=self.difficulty,
            source_chapter=self.source_chapter,
            source_chapter_index=self.source_chapter_index,
            source_section=self.source_section,
            source_quote=self.source_quote,
            status=self.status,
            tags=self.tags + ["reverse"],
            is_reverse=True,
            original_card_id=self.id,
        )


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
    images: list[EpubImage] = Field(default_factory=list, description="All images from the EPUB")

    @property
    def total_words(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    @property
    def total_images(self) -> int:
        return len(self.images)


class ChapterDensityConfig(BaseModel):
    """Per-chapter density configuration."""

    chapter_index: int = Field(description="Chapter index (0-indexed)")
    density: Density = Field(description="Density for this chapter")


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
    chapter_densities: list[ChapterDensityConfig] = Field(
        default_factory=list,
        description="Per-chapter density overrides"
    )
    deck_config: DeckConfig = Field(
        default_factory=DeckConfig,
        description="Deck export configuration"
    )

    def get_chapter_density(self, chapter_index: int) -> Density:
        """Get the density for a specific chapter, using override if set."""
        for config in self.chapter_densities:
            if config.chapter_index == chapter_index:
                return config.density
        return self.density

    def set_chapter_density(self, chapter_index: int, density: Density) -> None:
        """Set density for a specific chapter."""
        # Remove existing config for this chapter if any
        self.chapter_densities = [
            c for c in self.chapter_densities if c.chapter_index != chapter_index
        ]
        self.chapter_densities.append(
            ChapterDensityConfig(chapter_index=chapter_index, density=density)
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
