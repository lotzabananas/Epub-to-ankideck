"""Export cards to Anki .apkg format with advanced features."""

import hashlib
import json
from pathlib import Path
from typing import Optional

import genanki

from ..models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardTemplate,
    ChapterCards,
    DeckConfig,
    EpubImage,
)

# Default CSS styling for cards
DEFAULT_CARD_CSS = """
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

.night_mode .answer {
    border-top-color: #333;
}

img {
    max-width: 100%;
    height: auto;
}
"""

# Default Q&A Card template
DEFAULT_QA_FRONT = """
<div class="question">{{Question}}</div>
"""

DEFAULT_QA_BACK = """
<div class="question">{{Question}}</div>
<hr id="answer">
<div class="answer">{{Answer}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""

# Reverse Q&A template (Answer -> Question)
REVERSE_QA_FRONT = """
<div class="question">{{Answer}}</div>
"""

REVERSE_QA_BACK = """
<div class="question">{{Answer}}</div>
<hr id="answer">
<div class="answer">{{Question}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
    <span class="reverse-tag">[Reverse]</span>
</div>
"""

# Default Cloze card template
DEFAULT_CLOZE_FRONT = """
<div class="cloze-text">{{cloze:Text}}</div>
"""

DEFAULT_CLOZE_BACK = """
<div class="cloze-text">{{cloze:Text}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""


def generate_model_id(name: str) -> int:
    """Generate a stable model ID from a name."""
    hash_bytes = hashlib.md5(name.encode()).digest()
    return int.from_bytes(hash_bytes[:4], byteorder="big")


def generate_deck_id(name: str) -> int:
    """Generate a stable deck ID from a name."""
    hash_bytes = hashlib.md5(f"deck_{name}".encode()).digest()
    return int.from_bytes(hash_bytes[:4], byteorder="big")


def create_qa_model(
    deck_name: str,
    template: Optional[CardTemplate] = None,
    include_reverse: bool = False,
) -> genanki.Model:
    """Create the Q&A note model with optional custom template."""
    model_name = f"{deck_name} - Q&A"

    if template:
        front_html = template.front_html
        back_html = template.back_html
        css = template.css
    else:
        front_html = DEFAULT_QA_FRONT
        back_html = DEFAULT_QA_BACK
        css = DEFAULT_CARD_CSS

    templates = [
        {
            "name": "Card 1",
            "qfmt": front_html,
            "afmt": back_html,
        },
    ]

    # Add reverse card template if requested
    if include_reverse:
        templates.append({
            "name": "Card 2 (Reverse)",
            "qfmt": REVERSE_QA_FRONT,
            "afmt": REVERSE_QA_BACK,
        })

    return genanki.Model(
        generate_model_id(model_name),
        model_name,
        fields=[
            {"name": "Question"},
            {"name": "Answer"},
            {"name": "SourceChapter"},
            {"name": "SourceSection"},
            {"name": "Importance"},
            {"name": "Difficulty"},
            {"name": "CardID"},
        ],
        templates=templates,
        css=css,
    )


def create_cloze_model(
    deck_name: str,
    template: Optional[CardTemplate] = None,
) -> genanki.Model:
    """Create the Cloze note model with optional custom template."""
    model_name = f"{deck_name} - Cloze"

    if template:
        front_html = template.front_html
        back_html = template.back_html
        css = template.css
    else:
        front_html = DEFAULT_CLOZE_FRONT
        back_html = DEFAULT_CLOZE_BACK
        css = DEFAULT_CARD_CSS

    return genanki.Model(
        generate_model_id(model_name),
        model_name,
        model_type=genanki.Model.CLOZE,
        fields=[
            {"name": "Text"},
            {"name": "SourceChapter"},
            {"name": "SourceSection"},
            {"name": "Importance"},
            {"name": "Difficulty"},
            {"name": "CardID"},
        ],
        templates=[
            {
                "name": "Cloze",
                "qfmt": front_html,
                "afmt": back_html,
            },
        ],
        css=css,
    )


class AnkiExporter:
    """Export cards to Anki .apkg format with advanced features."""

    def __init__(
        self,
        deck_name: str,
        config: Optional[DeckConfig] = None,
    ):
        """
        Initialize the exporter.

        Args:
            deck_name: Name for the Anki deck
            config: Optional DeckConfig for customization
        """
        self.deck_name = deck_name
        self.config = config or DeckConfig()

        # Apply parent deck if configured
        if self.config.parent_deck:
            self.deck_name = f"{self.config.parent_deck}::{deck_name}"

        self.deck = genanki.Deck(generate_deck_id(self.deck_name), self.deck_name)

        # Create subdecks dict for chapter organization
        self.subdecks: dict[str, genanki.Deck] = {}

        # Create models with custom templates if provided
        self.qa_model = create_qa_model(
            self.deck_name,
            self.config.qa_template,
            self.config.include_reverse,
        )
        self.cloze_model = create_cloze_model(
            self.deck_name,
            self.config.cloze_template,
        )

        # Track media files (images)
        self.media_files: list[str] = []

    def _get_or_create_subdeck(self, chapter_title: str, chapter_index: int) -> genanki.Deck:
        """Get or create a subdeck for a chapter."""
        if not self.config.create_subdecks:
            return self.deck

        subdeck_name = self.config.get_chapter_deck_name(
            self.deck_name, chapter_title, chapter_index
        )

        if subdeck_name not in self.subdecks:
            self.subdecks[subdeck_name] = genanki.Deck(
                generate_deck_id(subdeck_name),
                subdeck_name,
            )

        return self.subdecks[subdeck_name]

    def _card_to_qa_note(self, card: Card) -> genanki.Note:
        """Convert a Q&A card to an Anki note."""
        return genanki.Note(
            model=self.qa_model,
            fields=[
                card.question or "",
                card.answer or "",
                card.source_chapter,
                card.source_section or "",
                str(card.importance),
                str(card.difficulty),
                card.id,
            ],
            tags=card.tags,
        )

    def _card_to_cloze_note(self, card: Card) -> genanki.Note:
        """Convert a Cloze card to an Anki note."""
        return genanki.Note(
            model=self.cloze_model,
            fields=[
                card.cloze_text or "",
                card.source_chapter,
                card.source_section or "",
                str(card.importance),
                str(card.difficulty),
                card.id,
            ],
            tags=card.tags,
        )

    def add_card(
        self,
        card: Card,
        target_deck: Optional[genanki.Deck] = None,
    ) -> None:
        """Add a single card to the deck."""
        deck = target_deck or self.deck

        if card.format == CardFormat.QA:
            note = self._card_to_qa_note(card)
        else:
            note = self._card_to_cloze_note(card)

        deck.add_note(note)

    def add_chapter_cards(
        self,
        chapter_cards: ChapterCards,
        include_excluded: bool = False,
        generate_reverse: bool = False,
    ) -> int:
        """
        Add all cards from a chapter to the deck.

        Args:
            chapter_cards: ChapterCards to add
            include_excluded: If True, also add excluded cards (with 'excluded' tag)
            generate_reverse: If True, create reverse cards for Q&A cards

        Returns:
            Number of cards added
        """
        # Get target deck (main or subdeck)
        target_deck = self._get_or_create_subdeck(
            chapter_cards.chapter.title,
            chapter_cards.chapter.index,
        )

        count = 0
        for card in chapter_cards.cards:
            if card.status == CardStatus.INCLUDED:
                self.add_card(card, target_deck)
                count += 1

                # Generate reverse card if configured and card is Q&A
                should_reverse = generate_reverse or self.config.include_reverse
                if should_reverse and card.format == CardFormat.QA:
                    reverse = card.create_reverse()
                    if reverse:
                        self.add_card(reverse, target_deck)
                        count += 1

            elif include_excluded:
                # Create a copy of the card with the excluded tag to avoid mutation
                excluded_card = card.model_copy(deep=True)
                excluded_card.tags = excluded_card.tags + ["status::excluded"]
                self.add_card(excluded_card, target_deck)
                count += 1

        return count

    def add_images(self, images: list[EpubImage], temp_dir: Path) -> list[str]:
        """
        Prepare images for export.

        Args:
            images: List of EpubImage objects
            temp_dir: Directory to write temporary image files

        Returns:
            List of media file paths
        """
        if not self.config.extract_images:
            return []

        temp_dir.mkdir(parents=True, exist_ok=True)
        media_paths = []

        for img in images:
            # Write image to temp file
            img_path = temp_dir / img.filename
            img_path.write_bytes(img.data)
            media_paths.append(str(img_path))

        self.media_files.extend(media_paths)
        return media_paths

    def export(self, output_path: str | Path) -> Path:
        """
        Export the deck to an .apkg file.

        Args:
            output_path: Path for the output file

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect all decks (main + subdecks)
        all_decks = [self.deck] + list(self.subdecks.values())

        # Create package with media if any
        if self.media_files:
            package = genanki.Package(all_decks)
            package.media_files = self.media_files
            package.write_to_file(str(output_path))
        else:
            genanki.Package(all_decks).write_to_file(str(output_path))

        return output_path


class MultiBookExporter:
    """Export multiple books into a single Anki deck or package."""

    def __init__(
        self,
        parent_deck_name: str,
        config: Optional[DeckConfig] = None,
    ):
        """
        Initialize the multi-book exporter.

        Args:
            parent_deck_name: Name for the parent deck containing all books
            config: Optional DeckConfig for customization
        """
        self.parent_deck_name = parent_deck_name
        self.config = config or DeckConfig()

        # Override parent deck in config
        self.config.parent_deck = parent_deck_name

        # Track books and their exporters
        self.book_exporters: dict[str, AnkiExporter] = {}
        self.all_media_files: list[str] = []

    def add_book(
        self,
        book: Book,
        chapter_cards_list: list[ChapterCards],
        include_excluded: bool = False,
        generate_reverse: bool = False,
    ) -> int:
        """
        Add a book's cards to the multi-book deck.

        Args:
            book: The Book object
            chapter_cards_list: List of ChapterCards for each chapter
            include_excluded: Include excluded cards with tag
            generate_reverse: Generate reverse Q&A cards

        Returns:
            Number of cards added from this book
        """
        # Create book-specific config with parent deck set
        book_config = self.config.model_copy(deep=True)
        book_deck_name = f"{book.title} - {book.author}"

        exporter = AnkiExporter(book_deck_name, book_config)
        self.book_exporters[book.title] = exporter

        total_cards = 0
        for chapter_cards in chapter_cards_list:
            count = exporter.add_chapter_cards(
                chapter_cards,
                include_excluded=include_excluded,
                generate_reverse=generate_reverse,
            )
            total_cards += count

        # Collect media files
        self.all_media_files.extend(exporter.media_files)

        return total_cards

    def export(self, output_path: str | Path) -> Path:
        """
        Export all books to a single .apkg file.

        Args:
            output_path: Path for the output file

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect all decks from all exporters
        all_decks = []
        for exporter in self.book_exporters.values():
            all_decks.append(exporter.deck)
            all_decks.extend(exporter.subdecks.values())

        # Create package
        if self.all_media_files:
            package = genanki.Package(all_decks)
            package.media_files = self.all_media_files
            package.write_to_file(str(output_path))
        else:
            genanki.Package(all_decks).write_to_file(str(output_path))

        return output_path

    def get_summary(self) -> dict:
        """Get summary of all books in the package."""
        return {
            "parent_deck": self.parent_deck_name,
            "books": len(self.book_exporters),
            "book_names": list(self.book_exporters.keys()),
            "total_media_files": len(self.all_media_files),
        }


def export_cards_to_json(
    chapter_cards_list: list[ChapterCards],
    output_dir: Path,
    book_title: str,
) -> dict[str, Path]:
    """
    Export cards to JSON files for persistence.

    Creates:
    - included/ directory with included cards per chapter
    - excluded/ directory with excluded cards per chapter
    - metadata.json with processing info

    Args:
        chapter_cards_list: List of ChapterCards to export
        output_dir: Base output directory
        book_title: Title of the book

    Returns:
        Dict mapping file type to paths created
    """
    output_dir = Path(output_dir)
    included_dir = output_dir / "included"
    excluded_dir = output_dir / "excluded"

    included_dir.mkdir(parents=True, exist_ok=True)
    excluded_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    total_included = 0
    total_excluded = 0

    for chapter_cards in chapter_cards_list:
        chapter_idx = chapter_cards.chapter.index
        filename = f"chapter_{chapter_idx + 1:02d}.json"

        # Export included cards
        included = [c.model_dump(mode="json") for c in chapter_cards.included_cards]
        if included:
            path = included_dir / filename
            path.write_text(json.dumps(included, indent=2, default=str))
            paths[f"included_{chapter_idx}"] = path
        total_included += len(included)

        # Export excluded cards
        excluded = [c.model_dump(mode="json") for c in chapter_cards.excluded_cards]
        if excluded:
            path = excluded_dir / filename
            path.write_text(json.dumps(excluded, indent=2, default=str))
            paths[f"excluded_{chapter_idx}"] = path
        total_excluded += len(excluded)

    # Create metadata
    metadata = {
        "book_title": book_title,
        "total_cards": total_included + total_excluded,
        "included_cards": total_included,
        "excluded_cards": total_excluded,
        "chapters_processed": len(chapter_cards_list),
    }

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))
    paths["metadata"] = meta_path

    return paths
