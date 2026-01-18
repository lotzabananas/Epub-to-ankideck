"""Export cards to Anki .apkg format."""

import hashlib
import json
import re
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
    DeckMetadata,
    ImageRef,
)

# Default CSS styling for cards
DEFAULT_CSS = """
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

.card-image {
    max-width: 100%;
    height: auto;
    margin: 10px 0;
}

.reverse-indicator {
    font-size: 10px;
    color: #999;
    margin-bottom: 10px;
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
"""

# Default Q&A Card template
QA_FRONT_DEFAULT = """
<div class="question">{{Question}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}
"""

QA_BACK_DEFAULT = """
<div class="question">{{Question}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}
<hr id="answer">
<div class="answer">{{Answer}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""

# Reverse Q&A Card template (Answer → Question)
QA_REVERSE_FRONT = """
<div class="reverse-indicator">[Reverse Card]</div>
<div class="question">{{Answer}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}
"""

QA_REVERSE_BACK = """
<div class="reverse-indicator">[Reverse Card]</div>
<div class="question">{{Answer}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}
<hr id="answer">
<div class="answer">{{Question}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""

# Default Cloze card template
CLOZE_FRONT_DEFAULT = """
<div class="cloze-text">{{cloze:Text}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}
"""

CLOZE_BACK_DEFAULT = """
<div class="cloze-text">{{cloze:Text}}</div>
{{#Image}}<div class="card-image"><img src="{{Image}}"></div>{{/Image}}

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""

# Legacy names for backward compatibility
CARD_CSS = DEFAULT_CSS
QA_FRONT = QA_FRONT_DEFAULT
QA_BACK = QA_BACK_DEFAULT
CLOZE_FRONT = CLOZE_FRONT_DEFAULT
CLOZE_BACK = CLOZE_BACK_DEFAULT


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
    include_reverse: bool = False,
    custom_template: Optional[CardTemplate] = None,
    custom_css: Optional[str] = None,
) -> genanki.Model:
    """Create the Q&A note model with optional reverse card."""
    model_name = f"{deck_name} - Q&A"

    css = custom_css or DEFAULT_CSS
    if custom_template and custom_template.css:
        css = custom_template.css

    front_html = custom_template.front_html if custom_template else QA_FRONT_DEFAULT
    back_html = custom_template.back_html if custom_template else QA_BACK_DEFAULT

    templates = [
        {
            "name": "Card 1",
            "qfmt": front_html,
            "afmt": back_html,
        },
    ]

    # Add reverse template if requested
    if include_reverse:
        templates.append({
            "name": "Card 2 (Reverse)",
            "qfmt": QA_REVERSE_FRONT,
            "afmt": QA_REVERSE_BACK,
        })

    return genanki.Model(
        generate_model_id(model_name + ("_rev" if include_reverse else "")),
        model_name,
        fields=[
            {"name": "Question"},
            {"name": "Answer"},
            {"name": "Image"},
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
    custom_template: Optional[CardTemplate] = None,
    custom_css: Optional[str] = None,
) -> genanki.Model:
    """Create the Cloze note model."""
    model_name = f"{deck_name} - Cloze"

    css = custom_css or DEFAULT_CSS
    if custom_template and custom_template.css:
        css = custom_template.css

    front_html = custom_template.front_html if custom_template else CLOZE_FRONT_DEFAULT
    back_html = custom_template.back_html if custom_template else CLOZE_BACK_DEFAULT

    return genanki.Model(
        generate_model_id(model_name),
        model_name,
        model_type=genanki.Model.CLOZE,
        fields=[
            {"name": "Text"},
            {"name": "Image"},
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
    """Export cards to Anki .apkg format."""

    def __init__(
        self,
        deck_name: str,
        config: Optional[DeckConfig] = None,
    ):
        """
        Initialize the exporter.

        Args:
            deck_name: Name for the Anki deck
            config: Optional deck configuration for advanced features
        """
        self.config = config or DeckConfig()
        self.base_deck_name = deck_name

        # Build full deck name with parent if specified
        if self.config.parent_deck:
            self.deck_name = f"{self.config.parent_deck}::{deck_name}"
        else:
            self.deck_name = deck_name

        # Main deck (may have subdecks added later)
        self.deck = genanki.Deck(generate_deck_id(self.deck_name), self.deck_name)

        # Subdecks by chapter (if enabled)
        self.subdecks: dict[int, genanki.Deck] = {}

        # Create models
        self.qa_model = create_qa_model(
            self.deck_name,
            include_reverse=self.config.include_reverse_cards,
            custom_template=self.config.custom_qa_template,
            custom_css=self.config.custom_css,
        )
        self.cloze_model = create_cloze_model(
            self.deck_name,
            custom_template=self.config.custom_cloze_template,
            custom_css=self.config.custom_css,
        )

        # Media files (images)
        self.media_files: list[str] = []
        self.image_data: dict[str, bytes] = {}

    def _get_deck_for_chapter(self, chapter_index: int, chapter_title: str) -> genanki.Deck:
        """Get the appropriate deck for a chapter (main or subdeck)."""
        if not self.config.use_chapter_subdecks:
            return self.deck

        if chapter_index not in self.subdecks:
            # Create subdeck with sanitized name
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in chapter_title
            )[:50]
            subdeck_name = f"{self.deck_name}::Ch{chapter_index + 1} - {safe_title}"
            self.subdecks[chapter_index] = genanki.Deck(
                generate_deck_id(subdeck_name),
                subdeck_name,
            )

        return self.subdecks[chapter_index]

    def add_image(self, image_id: str, filename: str, data: bytes) -> str:
        """
        Add an image to the media collection.

        Args:
            image_id: Unique ID for the image
            filename: Filename for the image
            data: Binary image data

        Returns:
            Filename to use in card HTML
        """
        # Sanitize filename
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        self.media_files.append(safe_filename)
        self.image_data[safe_filename] = data
        return safe_filename

    def _card_to_qa_note(
        self,
        card: Card,
        image_filename: Optional[str] = None,
    ) -> genanki.Note:
        """Convert a Q&A card to an Anki note."""
        return genanki.Note(
            model=self.qa_model,
            fields=[
                card.question or "",
                card.answer or "",
                image_filename or "",
                card.source_chapter,
                card.source_section or "",
                str(card.importance),
                str(card.difficulty),
                card.id,
            ],
            tags=card.tags,
        )

    def _card_to_cloze_note(
        self,
        card: Card,
        image_filename: Optional[str] = None,
    ) -> genanki.Note:
        """Convert a Cloze card to an Anki note."""
        return genanki.Note(
            model=self.cloze_model,
            fields=[
                card.cloze_text or "",
                image_filename or "",
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
        deck: Optional[genanki.Deck] = None,
        image_filename: Optional[str] = None,
    ) -> None:
        """Add a single card to the deck."""
        target_deck = deck or self.deck

        if card.format == CardFormat.QA:
            note = self._card_to_qa_note(card, image_filename)
        else:
            note = self._card_to_cloze_note(card, image_filename)

        target_deck.add_note(note)

    def add_chapter_cards(
        self,
        chapter_cards: ChapterCards,
        include_excluded: bool = False,
        book: Optional[Book] = None,
    ) -> int:
        """
        Add all cards from a chapter to the deck.

        Args:
            chapter_cards: ChapterCards to add
            include_excluded: If True, also add excluded cards (with 'excluded' tag)
            book: Optional Book for image lookup

        Returns:
            Number of cards added
        """
        # Get appropriate deck (main or subdeck)
        deck = self._get_deck_for_chapter(
            chapter_cards.chapter.index,
            chapter_cards.chapter.title,
        )

        count = 0
        for card in chapter_cards.cards:
            # Get image filename if card has an image
            image_filename = None
            if card.image_id and book:
                image_ref = book.get_image(card.image_id)
                if image_ref and image_ref.filename in self.image_data:
                    image_filename = image_ref.filename

            if card.status == CardStatus.INCLUDED:
                self.add_card(card, deck, image_filename)
                count += 1
            elif include_excluded:
                # Create a copy of the card with the excluded tag to avoid mutation
                excluded_card = card.model_copy(deep=True)
                excluded_card.tags = excluded_card.tags + ["status::excluded"]
                self.add_card(excluded_card, deck, image_filename)
                count += 1

        return count

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

        # Collect all decks
        all_decks = [self.deck] + list(self.subdecks.values())

        # Create package with media if present
        if self.image_data:
            # Write media files temporarily
            media_paths = []
            temp_dir = output_path.parent / ".temp_media"
            temp_dir.mkdir(exist_ok=True)

            for filename, data in self.image_data.items():
                media_path = temp_dir / filename
                media_path.write_bytes(data)
                media_paths.append(str(media_path))

            package = genanki.Package(all_decks)
            package.media_files = media_paths
            package.write_to_file(str(output_path))

            # Clean up temp files
            for path in media_paths:
                Path(path).unlink(missing_ok=True)
            temp_dir.rmdir()
        else:
            genanki.Package(all_decks).write_to_file(str(output_path))

        return output_path


class MultiBookExporter:
    """Export multiple books to a single Anki package with subdecks."""

    def __init__(
        self,
        master_deck_name: str,
        config: Optional[DeckConfig] = None,
    ):
        """
        Initialize multi-book exporter.

        Args:
            master_deck_name: Name for the master deck (e.g., "My Library")
            config: Optional deck configuration
        """
        self.master_deck_name = master_deck_name
        self.base_config = config or DeckConfig()

        # Book exporters
        self.book_exporters: dict[str, AnkiExporter] = {}

    def add_book(
        self,
        book: Book,
        chapter_cards_list: list[ChapterCards],
        include_excluded: bool = False,
    ) -> int:
        """
        Add a book to the multi-book package.

        Args:
            book: Book metadata
            chapter_cards_list: All chapter cards for the book
            include_excluded: Include excluded cards

        Returns:
            Number of cards added
        """
        # Create deck name for this book
        deck_name = f"{book.title} - {book.author}"

        # Create config with parent deck
        book_config = self.base_config.model_copy()
        book_config.parent_deck = self.master_deck_name

        # Create exporter for this book
        exporter = AnkiExporter(deck_name, book_config)
        self.book_exporters[book.title] = exporter

        # Add cards
        total = 0
        for cc in chapter_cards_list:
            total += exporter.add_chapter_cards(cc, include_excluded, book)

        return total

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
        all_media = {}

        for exporter in self.book_exporters.values():
            all_decks.append(exporter.deck)
            all_decks.extend(exporter.subdecks.values())
            all_media.update(exporter.image_data)

        # Export with media if present
        if all_media:
            temp_dir = output_path.parent / ".temp_media"
            temp_dir.mkdir(exist_ok=True)

            media_paths = []
            for filename, data in all_media.items():
                media_path = temp_dir / filename
                media_path.write_bytes(data)
                media_paths.append(str(media_path))

            package = genanki.Package(all_decks)
            package.media_files = media_paths
            package.write_to_file(str(output_path))

            for path in media_paths:
                Path(path).unlink(missing_ok=True)
            temp_dir.rmdir()
        else:
            genanki.Package(all_decks).write_to_file(str(output_path))

        return output_path


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
        included = [c.model_dump() for c in chapter_cards.included_cards]
        if included:
            path = included_dir / filename
            path.write_text(json.dumps(included, indent=2, default=str))
            paths[f"included_{chapter_idx}"] = path
        total_included += len(included)

        # Export excluded cards
        excluded = [c.model_dump() for c in chapter_cards.excluded_cards]
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
